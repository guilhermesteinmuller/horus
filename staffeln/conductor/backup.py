import parse
import staffeln.conf
import collections
from staffeln.common import constants
from staffeln.conductor import result
from openstack.exceptions import ResourceNotFound as OpenstackResourceNotFound
from openstack.exceptions import SDKException as OpenstackSDKException
from oslo_log import log
from staffeln.common import auth
from staffeln.common import context
from staffeln import objects
from staffeln.i18n import _
from staffeln.common import openstack as openstacksdk

CONF = staffeln.conf.CONF
LOG = log.getLogger(__name__)

BackupMapping = collections.namedtuple(
    "BackupMapping", ["volume_id", "backup_id", "project_id", "instance_id", "backup_completed"]
)

QueueMapping = collections.namedtuple(
    "QueueMapping", ["volume_id", "backup_id", "project_id", "instance_id", "backup_status"]
)


def check_vm_backup_metadata(metadata):
    if not CONF.conductor.backup_metadata_key in metadata:
        return False
    return metadata[CONF.conductor.backup_metadata_key].lower() in ["true"]


class Backup(object):
    """Implmentations of the queue with the sql."""

    def __init__(self):
        self.ctx = context.make_context()
        self.result = result.BackupResult()

    def publish_backup_result(self):
        self.result.publish()

    def get_backups(self, filters=None):
        return objects.Volume.list(self.ctx, filters=filters)

    def get_backup_quota(self, project_id):
        return openstacksdk.get_backup_quota(project_id)

    def get_queues(self, filters=None):
        """Get the list of volume queue columns from the queue_data table"""
        queues = objects.Queue.list(self.ctx, filters=filters)
        return queues

    def create_queue(self, old_tasks):
        """Create the queue of all the volumes for backup"""
        # 1. get the old task list, not finished in the last cycle
        #  and keep till now
        old_task_volume_list = []
        for old_task in old_tasks:
            old_task_volume_list.append(old_task.volume_id)

        # 2. add new tasks in the queue which are not existing in the old task list
        queue_list = self.check_instance_volumes()
        for queue in queue_list:
            if not queue.volume_id in old_task_volume_list:
                self._volume_queue(queue)

    # Backup the volumes attached to which has a specific metadata
    def filter_by_server_metadata(self, metadata):

        if not CONF.conductor.backup_metadata_key in metadata:
            return False

        return metadata[CONF.conductor.backup_metadata_key].lower() == constants.BACKUP_ENABLED_KEY

    # Backup the volumes in in-use and available status
    def filter_by_volume_status(self, volume_id, project_id):
        try:
            volume = openstacksdk.get_volume(volume_id, project_id)
            if volume == None: return False
            res = volume['status'] in ("available", "in-use")
            if not res:
                reason = _("Volume %s is not backed because it is in %s status" % (volume_id, volume['status']))
                LOG.info(reason)
                self.result.add_failed_backup(project_id, volume_id, reason)
            return res

        except OpenstackResourceNotFound:
            return False

    #  delete all backups forcily regardless of the status
    def hard_cancel_backup_task(self, task):
        try:
            reason = _("Cancel backup %s because of timeout." % task.backup_id)
            LOG.info(reason)
            backup = openstacksdk.get_backup(task.backup_id)
            if backup == None: return task.delete_queue()
            openstacksdk.delete_backup(task.backup_id)
            task.delete_queue()
            self.result.add_failed_backup(task.project_id, task.volume_id, reason)
        except OpenstackResourceNotFound:
            task.delete_queue()

        except OpenstackSDKException as e:
            reason = _("Backup %s deletion failed."
                       "%s" % (task.backup_id, str(e)))
            LOG.info(reason)
            # TODO(Alex): If backup timeout and also back cancel failed,
            #  then what to do?
            # 1. notify
            # 2. set the volume status as in-use
            # remove from the queue table
            task.delete_queue()
            self.result.add_failed_backup(task.project_id, task.volume_id, reason)

    #  delete only available backups
    def soft_remove_backup_task(self, backup_object):
        try:
            backup = openstacksdk.get_backup(backup_object.backup_id)
            if backup == None: return backup_object.delete_backup()
            if backup["status"] in ("available"):
                openstacksdk.delete_backup(backup_object.backup_id)
                backup_object.delete_backup()
            elif backup["status"] in ("error", "error_restoring"):
                # TODO(Alex): need to discuss
                #  now if backup is in error status, then retention service
                #  does not remove it from openstack but removes it from the
                #  backup table so user can delete it on Horizon.
                backup_object.delete_backup()
            else:  # "deleting", "restoring"
                LOG.info(_("Rotation for the backup %s is skipped in this cycle "
                           "because it is in %s status") % (backup_object.backup_id, backup["status"]))

        except OpenstackResourceNotFound:
            LOG.info(_("Backup %s is not existing in Openstack."
                       "Or cinder-backup is not existing in the cloud." % backup_object.backup_id))
            # remove from the backup table
            backup_object.delete_backup()
            return False

        except OpenstackSDKException as e:
            LOG.info(_("Backup %s deletion failed."
                       "%s" % (backup_object.backup_id, str(e))))
            # TODO(Alex): Add it into the notification queue
            # remove from the backup table
            backup_object.delete_backup()
            return False

    #  delete all backups forcily regardless of the status
    def hard_remove_volume_backup(self, backup_object):
        try:
            backup = openstacksdk.get_backup(uuid=backup_object.backup_id,
                                             project_id=backup_object.project_id)
            if backup == None: return backup_object.delete_backup()

            openstacksdk.delete_backup(uuid=backup_object.backup_id)
            backup_object.delete_backup()

        except OpenstackResourceNotFound:
            LOG.info(_("Backup %s is not existing in Openstack."
                       "Or cinder-backup is not existing in the cloud." % backup_object.backup_id))
            # remove from the backup table
            backup_object.delete_backup()

        except OpenstackSDKException as e:
            LOG.info(_("Backup %s deletion failed."
                       "%s" % (backup_object.backup_id, str(e))))
            # TODO(Alex): Add it into the notification queue
            # remove from the backup table
            backup_object.delete_backup()

    def check_instance_volumes(self):
        """Get the list of all the volumes from the project using openstacksdk
        Function first list all the servers in the project and get the volumes
        that are attached to the instance.
        """
        queues_map = []
        projects = openstacksdk.get_projects()
        for project in projects:
            empty_project = True
            servers = openstacksdk.get_servers(project_id=project.id)
            for server in servers:
                if not self.filter_by_server_metadata(server.metadata): continue
                if empty_project:
                    empty_project = False
                    self.result.add_project(project.id, project.name)
                for volume in server.attached_volumes:
                    if not self.filter_by_volume_status(volume["id"], project.id): continue
                    queues_map.append(
                        QueueMapping(
                            project_id=project.id,
                            volume_id=volume["id"],
                            backup_id="NULL",
                            instance_id=server.id,
                            backup_status=constants.BACKUP_PLANNED,
                        )
                    )
        return queues_map

    def _volume_queue(self, task):
        """Saves the queue data to the database."""

        # TODO(Alex): Need to escalate discussion
        # When create the task list, need to check the WIP backup generators
        # which are created in the past backup cycle.
        # Then skip to create new tasks for the volumes whose backup is WIP
        volume_queue = objects.Queue(self.ctx)
        volume_queue.backup_id = task.backup_id
        volume_queue.volume_id = task.volume_id
        volume_queue.instance_id = task.instance_id
        volume_queue.project_id = task.project_id
        volume_queue.backup_status = task.backup_status
        volume_queue.create()

    def create_volume_backup(self, queue):
        """Initiate the backup of the volume
        :params: queue: Provide the map of the volume that needs
                  backup.
        This function will call the backupup api and change the
        backup_status and backup_id in the queue table.
        """
        backup_id = queue.backup_id
        if backup_id == "NULL":
            try:
                LOG.info(_("Backup for volume %s creating in project %s"
                           % (queue.volume_id, queue.project_id)))
                # NOTE(Alex): no need to wait because we have a cycle time out
                volume_backup = openstacksdk.create_backup(volume_id=queue.volume_id,
                                                           project_id=queue.project_id)
                queue.backup_id = volume_backup.id
                queue.backup_status = constants.BACKUP_WIP
                queue.save()
            except OpenstackSDKException as error:
                reason = _("Backup creation for the volume %s failled. %s"
                           % (queue.volume_id, str(error)))
                LOG.info(reason)
                self.result.add_failed_backup(queue.project_id, queue.volume_id, reason)
                parsed = parse.parse("Error in creating volume backup {id}", str(error))
                if parsed == None: return
                queue.backup_id = parsed["id"]
                queue.backup_status = constants.BACKUP_WIP
                queue.save()
        else:
            pass
            # TODO(Alex): remove this task from the task list
            #  Backup planned task cannot have backup_id in the same cycle
            #  Reserve for now because it is related to the WIP backup genenrators which
            #  are not finished in the current cycle

    def process_failed_backup(self, task):
        # 1. TODO(Alex): notify via email
        reason = _("The status of backup for the volume %s is error." % task.volume_id)
        self.result.add_failed_backup(task.project_id, task.volume_id, reason)
        LOG.error(reason)
        # 2. cancel volume backup
        self.hard_cancel_backup_task(task)
        # 3. remove failed task from the task queue
        task.delete_queue()

    def process_non_existing_backup(self, task):
        task.delete_queue()

    def process_available_backup(self, task):
        LOG.info("Backup of the volume %s is successful." % task.volume_id)
        # 1. save success backup in the backup table
        self._volume_backup(
            BackupMapping(
                volume_id=task.volume_id,
                project_id=task.project_id,
                backup_id=task.backup_id,
                instance_id=task.instance_id,
                backup_completed=1,
            )
        )
        self.result.add_success_backup(task.project_id, task.volume_id, task.backup_id)
        # 2. remove from the task list
        task.delete_queue()
        # 3. TODO(Alex): notify via email

    def process_using_backup(self, task):
        # treat same as the available backup for now
        self.process_available_backup(task)

    def check_volume_backup_status(self, queue):
        """Checks the backup status of the volume
        :params: queue: Provide the map of the volume that needs backup
                 status checked.
        Call the backups api to see if the backup is successful.
        """
        try:
            backup_gen = openstacksdk.get_backup(queue.backup_id)
            if backup_gen == None:
                # TODO(Alex): need to check when it is none
                LOG.info(_("[Beta] Backup status of %s is returning none." % (queue.backup_id)))
                self.process_non_existing_backup(queue)
                return
            if backup_gen.status == "error":
                self.process_failed_backup(queue)
            elif backup_gen.status == "available":
                self.process_available_backup(queue)
            elif backup_gen.status == "creating":
                LOG.info("Waiting for backup of %s to be completed" % queue.volume_id)
            else:  # "deleting", "restoring", "error_restoring" status
                self.process_using_backup(queue)
        except OpenstackResourceNotFound as e:
            self.process_non_existing_backup(queue)

    def _volume_backup(self, task):
        # matching_backups = [
        #     g for g in self.available_backups if g.backup_id == task.backup_id
        # ]
        # if not matching_backups:
        volume_backup = objects.Volume(self.ctx)
        volume_backup.backup_id = task.backup_id
        volume_backup.volume_id = task.volume_id
        volume_backup.instance_id = task.instance_id
        volume_backup.project_id = task.project_id
        volume_backup.backup_completed = task.backup_completed
        volume_backup.create()
