# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from unittest import mock

import tenacity
from openstack import exceptions as openstack_exc

from staffeln import conf
from staffeln.common import openstack as s_openstack
from staffeln.tests import base


class OpenstackSDKTest(base.TestCase):

    def setUp(self):
        super(OpenstackSDKTest, self).setUp()
        self.m_c = mock.MagicMock()
        with mock.patch("openstack.connect", return_value=self.m_c):
            self.openstack = s_openstack.OpenstackSDK()
        self.m_sleep = mock.Mock()
        func_list = [
            "get_user_id",
            "get_projects",
            "get_servers",
            "get_role_assignments",
            "get_user",
            "get_project_member_emails",
            "get_volume",
            "get_backup",
            "delete_backup",
            "get_backup_quota",
            "get_backup_gigabytes_quota",
        ]
        for i in func_list:
            getattr(self.openstack, i).retry.sleep = (  # pylint: disable=E1101
                self.m_sleep
            )
            getattr(self.openstack, i).retry.stop = (  # pylint: disable=E1101
                tenacity.stop_after_attempt(2)
            )

        self.fake_user = mock.MagicMock(id="foo", email="foo@foo.com")
        self.fake_volume = mock.MagicMock(id="fake_volume")
        self.fake_backup = mock.MagicMock(id="fake_backup")
        self.fake_role_assignment = mock.MagicMock(user="foo")
        self.fake_role_assignment2 = mock.MagicMock(user={"id": "bar"})

    def _test_http_error(self, m_func, retry_func, status_code, call_count=1, **kwargs):
        m_func.side_effect = openstack_exc.HttpException(http_status=status_code)
        exc = self.assertRaises(
            openstack_exc.HttpException,
            getattr(self.openstack, retry_func),
            **kwargs,
        )
        self.assertEqual(status_code, exc.status_code)
        skip_retry_codes = conf.CONF.openstack.skip_retry_codes
        if str(status_code) not in skip_retry_codes:
            if call_count == 1:
                self.m_sleep.assert_called_once_with(1.0)
            else:
                self.m_sleep.assert_has_calls(
                    [mock.call(1.0) for c in range(call_count)]
                )
        else:
            self.m_sleep.assert_not_called()

    def _test_non_http_error(self, m_func, retry_func, **kwargs):
        m_func.side_effect = KeyError
        self.assertRaises(KeyError, getattr(self.openstack, retry_func), **kwargs)
        self.m_sleep.assert_not_called()

    def test_get_servers(self):
        self.m_c.compute.servers = mock.MagicMock(return_value=[])
        self.assertEqual(self.openstack.get_servers(), [])
        self.m_c.compute.servers.assert_called_once_with(
            details=True, all_projects=True
        )

    def test_get_servers_non_http_error(self):
        self._test_non_http_error(self.m_c.compute.servers, "get_servers")

    def test_get_servers_conf_skip_http_error(self):
        conf.CONF.set_override("skip_retry_codes", [403], "openstack")
        self._test_http_error(self.m_c.compute.servers, "get_servers", status_code=403)
        self.assertEqual(["403"], conf.CONF.openstack.skip_retry_codes)

    def test_get_servers_conf_skip_http_error_not_hit(self):
        conf.CONF.set_override("skip_retry_codes", [403], "openstack")
        self._test_http_error(self.m_c.compute.servers, "get_servers", status_code=404)
        self.assertEqual(["403"], conf.CONF.openstack.skip_retry_codes)

    def test_get_servers_404_http_error(self):
        self._test_http_error(self.m_c.compute.servers, "get_servers", status_code=404)
        self.assertEqual(["404"], conf.CONF.openstack.skip_retry_codes)

    def test_get_servers_500_http_error(self):
        self._test_http_error(self.m_c.compute.servers, "get_servers", status_code=500)

    def test_get_projects(self):
        self.m_c.list_projects = mock.MagicMock(return_value=[])
        self.assertEqual(self.openstack.get_projects(), [])
        self.m_c.list_projects.assert_called_once_with()

    def test_get_projects_non_http_error(self):
        self._test_non_http_error(self.m_c.list_projects, "get_projects")

    def test_get_projects_404_http_error(self):
        self._test_http_error(self.m_c.list_projects, "get_projects", status_code=404)

    def test_get_projects_500_http_error(self):
        self._test_http_error(self.m_c.list_projects, "get_projects", status_code=500)

    def test_get_user_id(self):
        self.m_c.get_user = mock.MagicMock(return_value=self.fake_user)
        self.assertEqual(self.openstack.get_user_id(), "foo")
        self.m_c.get_user.assert_called_once_with(name_or_id=mock.ANY)

    def test_get_user_id_non_http_error(self):
        self._test_non_http_error(self.m_c.get_user, "get_user_id")

    def test_get_user_id_404_http_error(self):
        self._test_http_error(self.m_c.get_user, "get_user_id", status_code=404)

    def test_get_user_id_500_http_error(self):
        self._test_http_error(self.m_c.get_user, "get_user_id", status_code=500)

    def test_get_user(self):
        self.m_c.get_user = mock.MagicMock(return_value=self.fake_user)
        self.assertEqual(
            self.openstack.get_user(user_id=self.fake_user.id), self.fake_user
        )
        self.m_c.get_user.assert_called_once_with(name_or_id=self.fake_user.id)

    def test_get_user_non_http_error(self):
        self._test_non_http_error(
            self.m_c.get_user, "get_user", user_id=self.fake_user.id
        )

    def test_get_user_404_http_error(self):
        self._test_http_error(
            self.m_c.get_user,
            "get_user",
            status_code=404,
            user_id=self.fake_user.id,
        )

    def test_get_user_500_http_error(self):
        self._test_http_error(
            self.m_c.get_user,
            "get_user",
            status_code=500,
            user_id=self.fake_user.id,
        )

    def test_get_role_assignments(self):
        self.m_c.list_role_assignments = mock.MagicMock(return_value=[])
        self.assertEqual(self.openstack.get_role_assignments(project_id="foo"), [])
        self.m_c.list_role_assignments.assert_called_once_with(
            filters={"project": "foo"}
        )

    def test_get_role_assignments_non_http_error(self):
        self._test_non_http_error(
            self.m_c.list_role_assignments,
            "get_role_assignments",
            project_id="foo",
        )

    def test_get_role_assignments_404_http_error(self):
        self._test_http_error(
            self.m_c.list_role_assignments,
            "get_role_assignments",
            status_code=404,
            project_id="foo",
        )

    def test_get_role_assignments_500_http_error(self):
        self._test_http_error(
            self.m_c.list_role_assignments,
            "get_role_assignments",
            status_code=500,
            project_id="foo",
        )

    def test_get_project_member_emails(self):
        # Make sure we cover both get_user pattern
        self.m_c.list_role_assignments = mock.MagicMock(
            return_value=[
                self.fake_role_assignment,
                self.fake_role_assignment2,
            ]
        )
        self.m_c.get_user = mock.MagicMock(return_value=self.fake_user)
        self.assertEqual(
            self.openstack.get_project_member_emails(project_id="foo"),
            [self.fake_user.email, self.fake_user.email],
        )
        self.m_c.list_role_assignments.assert_called_once_with(
            filters={"project": "foo"}
        )
        self.m_c.get_user.assert_has_calls(
            [
                mock.call(name_or_id=self.fake_role_assignment.user),
                mock.call(name_or_id=self.fake_role_assignment2.user.get("id")),
            ]
        )

    def test_get_project_member_emails_non_http_error(self):
        self._test_non_http_error(
            self.m_c.list_role_assignments,
            "get_project_member_emails",
            project_id="foo",
        )

    def test_get_project_member_emails_404_http_error(self):
        self._test_http_error(
            self.m_c.list_role_assignments,
            "get_project_member_emails",
            status_code=404,
            project_id="foo",
        )

    def test_get_project_member_emails_500_http_error(self):
        self._test_http_error(
            self.m_c.list_role_assignments,
            "get_project_member_emails",
            status_code=500,
            call_count=3,
            project_id="foo",
        )

    def test_get_volume(self):
        self.m_c.get_volume_by_id = mock.MagicMock(return_value=self.fake_volume)
        self.assertEqual(
            self.openstack.get_volume(uuid=self.fake_volume.id, project_id="bar"),
            self.fake_volume,
        )
        self.m_c.get_volume_by_id.assert_called_once_with(self.fake_volume.id)

    def test_get_volume_non_http_error(self):
        self._test_non_http_error(
            self.m_c.get_volume_by_id,
            "get_volume",
            uuid="foo",
            project_id="bar",
        )

    def test_get_volume_404_http_error(self):
        self._test_http_error(
            self.m_c.get_volume_by_id,
            "get_volume",
            status_code=404,
            uuid="foo",
            project_id="bar",
        )

    def test_get_volume_500_http_error(self):
        self._test_http_error(
            self.m_c.get_volume_by_id,
            "get_volume",
            status_code=500,
            uuid="foo",
            project_id="bar",
        )

    def test_get_backup(self):
        self.m_c.get_volume_backup = mock.MagicMock(return_value=self.fake_backup)
        self.assertEqual(
            self.openstack.get_backup(uuid=self.fake_backup.id, project_id="bar"),
            self.fake_backup,
        )
        self.m_c.get_volume_backup.assert_called_once_with(self.fake_backup.id)

    def test_get_backup_not_found(self):
        self.m_c.get_volume_backup = mock.MagicMock(
            side_effect=openstack_exc.ResourceNotFound
        )
        self.assertEqual(
            self.openstack.get_backup(uuid=self.fake_backup.id, project_id="bar"),
            None,
        )
        self.m_c.get_volume_backup.assert_called_once_with(self.fake_backup.id)

    def test_get_backup_non_http_error(self):
        self._test_non_http_error(
            self.m_c.get_volume_backup,
            "get_backup",
            uuid="foo",
            project_id="bar",
        )

    def test_get_backup_404_http_error(self):
        self._test_http_error(
            self.m_c.get_volume_backup,
            "get_backup",
            status_code=404,
            uuid="foo",
            project_id="bar",
        )

    def test_get_backup_500_http_error(self):
        self._test_http_error(
            self.m_c.get_volume_backup,
            "get_backup",
            status_code=500,
            uuid="foo",
            project_id="bar",
        )

    def test_delete_backup(self):
        self.m_c.delete_volume_backup = mock.MagicMock(return_value=self.fake_backup)
        self.assertEqual(
            self.openstack.delete_backup(uuid=self.fake_backup.id, project_id="bar"),
            None,
        )
        self.m_c.delete_volume_backup.assert_called_once_with(
            self.fake_backup.id, force=False
        )

    def test_delete_backup_not_found(self):
        self.m_c.delete_volume_backup = mock.MagicMock(
            side_effect=openstack_exc.ResourceNotFound
        )
        self.assertEqual(
            self.openstack.delete_backup(uuid=self.fake_backup.id, project_id="bar"),
            None,
        )
        self.m_c.delete_volume_backup.assert_called_once_with(
            self.fake_backup.id, force=False
        )

    def test_delete_backup_non_http_error(self):
        self._test_non_http_error(
            self.m_c.delete_volume_backup,
            "delete_backup",
            uuid="foo",
            project_id="bar",
        )

    def test_delete_backup_404_http_error(self):
        self._test_http_error(
            self.m_c.delete_volume_backup,
            "delete_backup",
            status_code=404,
            uuid="foo",
            project_id="bar",
        )

    def test_delete_backup_500_http_error(self):
        self._test_http_error(
            self.m_c.delete_volume_backup,
            "delete_backup",
            status_code=500,
            uuid="foo",
            project_id="bar",
        )

    @mock.patch("openstack.proxy._json_response")
    def test_get_backup_quota(self, m_j_r):
        self.m_c.block_storage.get = mock.MagicMock(status_code=200)
        self.m_gam = mock.MagicMock()
        self.m_c._get_and_munchify = self.m_gam
        self.m_gam.return_value = mock.MagicMock(backups=[self.fake_backup.id])
        self.assertEqual(
            [self.fake_backup.id],
            self.openstack.get_backup_quota(project_id="bar"),
        )
        self.m_c.block_storage.get.assert_called_once_with(
            "/os-quota-sets/bar?usage=True"
        )

    def test_get_backup_quota_non_http_error(self):
        self._test_non_http_error(
            self.m_c.block_storage.get, "get_backup_quota", project_id="bar"
        )

    def test_get_backup_quota_404_http_error(self):
        self._test_http_error(
            self.m_c.block_storage.get,
            "get_backup_quota",
            status_code=404,
            project_id="bar",
        )

    def test_get_backup_quota_500_http_error(self):
        self._test_http_error(
            self.m_c.block_storage.get,
            "get_backup_quota",
            status_code=500,
            project_id="bar",
        )

    @mock.patch("openstack.proxy._json_response")
    def test_get_backup_gigabytes_quota(self, m_j_r):
        self.m_c.block_storage.get = mock.MagicMock(status_code=200)
        self.m_gam = mock.MagicMock()
        self.m_c._get_and_munchify = self.m_gam
        self.m_gam.return_value = mock.MagicMock(backup_gigabytes=[self.fake_backup.id])
        self.assertEqual(
            [self.fake_backup.id],
            self.openstack.get_backup_gigabytes_quota(project_id="bar"),
        )
        self.m_c.block_storage.get.assert_called_once_with(
            "/os-quota-sets/bar?usage=True"
        )

    def test_get_backup_gigabytes_quota_non_http_error(self):
        self._test_non_http_error(
            self.m_c.block_storage.get,
            "get_backup_gigabytes_quota",
            project_id="bar",
        )

    def test_get_backup_gigabytes_quota_404_http_error(self):
        self._test_http_error(
            self.m_c.block_storage.get,
            "get_backup_gigabytes_quota",
            status_code=404,
            project_id="bar",
        )

    def test_get_backup_gigabytes_quota_500_http_error(self):
        self._test_http_error(
            self.m_c.block_storage.get,
            "get_backup_gigabytes_quota",
            status_code=500,
            project_id="bar",
        )

    @mock.patch("openstack.proxy._json_response")
    def test_get_volume_quotas(self, m_j_r):
        self.m_c.block_storage.get = mock.MagicMock(status_code=200)
        self.m_gam_return = mock.MagicMock()
        self.m_gam = mock.MagicMock(return_value=self.m_gam_return)
        self.m_c._get_and_munchify = self.m_gam
        self.assertEqual(
            self.m_gam_return,
            self.openstack._get_volume_quotas(project_id="bar"),
        )
        self.m_c.block_storage.get.assert_called_once_with(
            "/os-quota-sets/bar?usage=True"
        )
        self.m_gam.assert_called_once_with("quota_set", m_j_r())

    @mock.patch("openstack.proxy._json_response")
    def test_get_volume_quotas_no_usage(self, m_j_r):
        self.m_c.block_storage.get = mock.MagicMock(status_code=200)
        self.m_gam_return = mock.MagicMock()
        self.m_gam = mock.MagicMock(return_value=self.m_gam_return)
        self.m_c._get_and_munchify = self.m_gam
        self.assertEqual(
            self.m_gam_return,
            self.openstack._get_volume_quotas(project_id="bar", usage=False),
        )
        self.m_c.block_storage.get.assert_called_once_with("/os-quota-sets/bar")
        self.m_gam.assert_called_once_with("quota_set", m_j_r())
