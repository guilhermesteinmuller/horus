from __future__ import annotations

from oslo_config import cfg

from staffeln.common import constants
from staffeln.i18n import _

conductor_group = cfg.OptGroup(
    "conductor",
    title="Conductor Options",
    help=_("Options under this group are used " "to define Conductor's configuration."),
)
openstack_group = cfg.OptGroup(
    "openstack",
    title="OpenStack Options",
    help=_(
        "Options under this group are used "
        "to define OpneStack related configuration."
    ),
)

backup_opts = [
    cfg.IntOpt(
        "backup_workers",
        default=1,
        help=_(
            "The maximum number of backup processes to "
            "fork and run. Default to number of CPUs on the host."
        ),
    ),
    cfg.IntOpt(
        "backup_service_period",
        default=1800,
        min=60,
        help=_("The time of backup period, the unit is one second."),
    ),
    cfg.IntOpt(
        "backup_min_interval",
        default=1800,
        min=0,
        help=_(
            "The time of minimum guaranteed interval between Staffeln "
            "created backups, the unit is one seconds. Set to 0 if don't "
            "need to enable this feature."
        ),
    ),
    cfg.IntOpt(
        "report_period",
        default=86400,
        min=600,
        help=_("The time of report period, the unit is one seconds."),
    ),
    cfg.StrOpt(
        "backup_cycle_timout",
        regex=(
            r"((?P<years>\d+?)y)?((?P<months>\d+?)mon)?((?P<weeks>\d+?)w)?"
            r"((?P<days>\d+?)d)?((?P<hours>\d+?)h)?((?P<minutes>\d+?)min)?"
            r"((?P<seconds>\d+?)s)?"
        ),
        default=constants.DEFAULT_BACKUP_CYCLE_TIMEOUT,
        help=_(
            "The duration while the backup cycle waits backups."
            "<YEARS>y<MONTHS>mon<WEEKS>w<DAYS>d<HOURS>h<MINUTES>min<SECONDS>s."
        ),
    ),
    cfg.StrOpt(
        "backup_metadata_key",
        help=_("The key string of metadata the VM, which requres back up, has"),
    ),
    cfg.StrOpt(
        "retention_metadata_key",
        help=_(
            "The key string of metadata the VM, which use as backup retention "
            "period."
        ),
    ),
    cfg.IntOpt(
        "full_backup_depth",
        default=2,
        min=0,
        help=_("Number of incremental backups between full backups."),
    ),
]

openstack_opts = [
    cfg.IntOpt(
        "retry_timeout",
        default=300,
        min=1,
        help=_(
            "The timeout for retry OpenStackSDK HTTP exceptions, "
            "the unit is one second."
        ),
    ),
    cfg.IntOpt(
        "max_retry_interval",
        default=30,
        min=0,
        help=_(
            "Max time interval for retry OpenStackSDK HTTP exceptions, "
            "the unit is one second."
        ),
    ),
    cfg.ListOpt(
        "skip_retry_codes",
        default=["404"],
        help=_(
            "A list of HTTP codes "
            "to skip retry on for OpenStackSDK HTTP "
            "exception."
        ),
    ),
]

rotation_opts = [
    cfg.IntOpt(
        "rotation_workers",
        default=1,
        help=_(
            "The maximum number of rotation processes to "
            "fork and run. Default to number of CPUs on the host."
        ),
    ),
    cfg.IntOpt(
        "retention_service_period",
        default=1200,
        min=60,
        help=_("The period of the retention service, the unit is one second."),
    ),
    cfg.IntOpt(
        "rotation_workers",
        default=1,
        help=_(
            "The maximum number of rotation processes to "
            "fork and run. Default to number of CPUs on the host."
        ),
    ),
    cfg.StrOpt(
        "retention_time",
        regex=(
            r"((?P<years>\d+?)y)?((?P<months>\d+?)mon)?((?P<weeks>\d+?)w)?"
            r"((?P<days>\d+?)d)?((?P<hours>\d+?)h)?((?P<minutes>\d+?)min)?"
            r"((?P<seconds>\d+?)s)?"
        ),
        default="2w3d",
        help=_(
            "The time of retention period, the for mat is "
            "<YEARS>y<MONTHS>mon<WEEKS>w<DAYS>d<HOURS>h<MINUTES>min<SECONDS>s."
        ),
    ),
]


coordination_group = cfg.OptGroup(
    "coordination",
    title="Coordination Options",
    help=_(
        "Options under this group are used to define Coordination's" "configuration."
    ),
)


coordination_opts = [
    cfg.StrOpt(
        "backend_url",
        default="",
        help=_("lock coordination connection backend URL."),
    ),
]


CONDUCTOR_OPTS = (backup_opts, rotation_opts)


def register_opts(conf):
    conf.register_group(conductor_group)
    conf.register_opts(backup_opts, group=conductor_group)
    conf.register_opts(rotation_opts, group=conductor_group)
    conf.register_opts(openstack_opts, group=openstack_group)
    conf.register_opts(coordination_opts, group=coordination_group)


def list_opts():
    return {
        "DEFAULT": rotation_opts,
        conductor_group: backup_opts,
        openstack_group: openstack_opts,
        coordination_group: coordination_opts,
    }
