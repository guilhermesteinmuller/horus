from staffeln.common import auth

conn = auth.create_connection()


# user
def get_user_id():
    user_name = conn.config.auth["username"]
    if "user_domain_id" in conn.config.auth:
        domain_id = conn.config.auth["user_domain_id"]
        user = conn.get_user(name_or_id=user_name, domain_id=domain_id)
    elif "user_domain_name" in conn.config.auth:
        domain_name = conn.config.auth["user_domain_name"]
        user = conn.get_user(name_or_id=user_name, domain_id=domain_name)
    else:
        user = conn.get_user(name_or_id=user_name)
    return user.id

############## project
def get_projects():
    conn.block_storage
    return conn.list_projects()


############## server
def get_servers(project_id, all_projects=True, details=True):
    return conn.compute.servers(details=details, all_projects=all_projects, project_id=project_id)


############## volume
def get_volume(uuid):
    # volume = conn.block_storage.get_volume(volume_id)
    return conn.get_volume_by_id(uuid)


############## backup
def get_backup(uuid, project_id=None):
    # return conn.block_storage.get_backup(
    #     project_id=project_id, backup_id=uuid,
    # )
    # conn.block_storage.backups(volume_id=uuid,project_id=project_id)
    return conn.get_volume_backup(uuid)


def create_backup(volume_id, force=True, wait=False):
    # return conn.block_storage.create_backup(
    #     volume_id=queue.volume_id, force=True, project_id=queue.project_id,
    # )
    return conn.create_volume_backup(
        volume_id=volume_id, force=force, wait=wait,
    )


def delete_backup(uuid, project_id=None, force=True):
    # TODO(Alex): v3 is not supporting force delete?
    # conn.block_storage.delete_backup(
    #     project_id=project_id, backup_id=uuid,
    # )
    conn.delete_volume_backup(uuid, force=force)
    # TODO(Alex): After delete the backup generator, need to set the volume status again