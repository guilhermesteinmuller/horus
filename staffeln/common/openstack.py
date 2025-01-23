from __future__ import annotations

import tenacity
from openstack import exceptions, proxy
from oslo_log import log

from staffeln import conf
from staffeln.common import auth
from staffeln.i18n import _

CONF = conf.CONF
LOG = log.getLogger(__name__)


class RetryHTTPError(tenacity.retry_if_exception):
    """Retry strategy that retries if the exception is an ``HTTPError`` with
    a abnormal status code.
    """

    def __init__(self):
        def is_http_error(exception):
            # Make sure we don't retry on codes in skip list (default: [404]),
            # as not found could be an expected status.
            skip_codes = CONF.openstack.skip_retry_codes
            result = (
                isinstance(exception, exceptions.HttpException)
                and str(exception.status_code) not in skip_codes
            )
            if result:
                LOG.debug(
                    f"Getting HttpException {exception} (status "
                    f"code: {exception.status_code}), "
                    "retry till timeout..."
                )
            return result

        super().__init__(predicate=is_http_error)


class OpenstackSDK:
    def __init__(self):
        self.conn_list = {}
        self.conn = auth.create_connection()

    def set_project(self, project):
        LOG.debug(_("Connect as project %s" % project.get("name")))
        project_id = project.get("id")

        if project_id not in self.conn_list:
            LOG.debug(_("Initiate connection for project %s" % project.get("name")))
            conn = self.conn.connect_as_project(project)
            self.conn_list[project_id] = conn
        LOG.debug(_("Connect as project %s" % project.get("name")))
        self.conn = self.conn_list[project_id]

    # user
    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def get_user_id(self):
        user_name = self.conn.config.auth["username"]
        if "user_domain_id" in self.conn.config.auth:
            domain_id = self.conn.config.auth["user_domain_id"]
            user = self.conn.get_user(name_or_id=user_name, domain_id=domain_id)
        elif "user_domain_name" in self.conn.config.auth:
            domain_name = self.conn.config.auth["user_domain_name"]
            user = self.conn.get_user(name_or_id=user_name, domain_id=domain_name)
        else:
            user = self.conn.get_user(name_or_id=user_name)
        return user.id

    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def get_role_assignments(self, project_id, user_id=None):
        filters = {"project": project_id}
        if user_id:
            filters["user"] = user_id
        return self.conn.list_role_assignments(filters=filters)

    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def get_user(self, user_id):
        return self.conn.get_user(name_or_id=user_id)

    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def get_project_member_emails(self, project_id):
        members = self.get_role_assignments(project_id)
        emails = []
        for member in members:
            if hasattr(member, "user"):
                user_id = None
                if type(member.user) is dict and "id" in member.user:
                    user_id = member.user["id"]
                elif type(member.user) is str:
                    user_id = member.user
                if user_id:
                    user = self.get_user(user_id)
                    if user and hasattr(user, "email") and user.email:
                        emails.append(user.email)
        return emails

    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def get_projects(self):
        return self.conn.list_projects()

    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def get_servers(self, project_id=None, all_projects=True, details=True):
        if project_id is not None:
            return self.conn.compute.servers(
                details=details,
                all_projects=all_projects,
                project_id=project_id,
            )
        else:
            return self.conn.compute.servers(details=details, all_projects=all_projects)

    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def get_volume(self, uuid, project_id):
        return self.conn.get_volume_by_id(uuid)

    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def get_backup(self, uuid, project_id=None):
        try:
            return self.conn.get_volume_backup(uuid)
        except exceptions.ResourceNotFound:
            return None

    def create_backup(
        self,
        volume_id,
        project_id,
        force=True,
        wait=False,
        name=None,
        incremental=False,
    ):
        return self.conn.create_volume_backup(
            volume_id=volume_id,
            force=force,
            wait=wait,
            name=name,
            incremental=incremental,
        )

    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def delete_backup(self, uuid, project_id=None, force=False):
        # Note(Alex): v3 is not supporting force delete?
        # conn.block_storage.delete_backup(
        #     project_id=project_id, backup_id=uuid,
        # )
        LOG.debug(f"Start deleting backup {uuid} in OpenStack.")
        try:
            self.conn.delete_volume_backup(uuid, force=force)
            # TODO(Alex): After delete the backup generator,
            # need to set the volume status again
        except exceptions.ResourceNotFound:
            return None

    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def get_backup_quota(self, project_id):
        # quota = conn.get_volume_quotas(project_id)
        quota = self._get_volume_quotas(project_id)
        return quota.backups

    @tenacity.retry(
        retry=RetryHTTPError(),
        wait=tenacity.wait_exponential(max=CONF.openstack.max_retry_interval),
        reraise=True,
        stop=tenacity.stop_after_delay(CONF.openstack.retry_timeout),
    )
    def get_backup_gigabytes_quota(self, project_id):
        # quota = conn.get_volume_quotas(project_id)
        quota = self._get_volume_quotas(project_id)
        return quota.backup_gigabytes

    # rewrite openstasdk._block_storage.get_volume_quotas
    # added usage flag
    # ref: https://docs.openstack.org/api-ref/block-storage/v3/?
    # expanded=#show-quota-usage-for-a-project
    def _get_volume_quotas(self, project_id, usage=True):
        """Get volume quotas for a project

        :param name_or_id: project name or id
        :raises: OpenStackCloudException if it's not a valid project

        :returns: Munch object with the quotas
        """

        if usage:
            resp = self.conn.block_storage.get(
                "/os-quota-sets/{project_id}?usage=True".format(project_id=project_id)
            )
        else:
            resp = self.conn.block_storage.get(
                "/os-quota-sets/{project_id}".format(project_id=project_id)
            )
        data = proxy._json_response(resp, error_message="cinder client call failed")
        return self.conn._get_and_munchify("quota_set", data)
