#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from sqlalchemy import Boolean, Column, DateTime, ForeignKey
from sqlalchemy import Integer, MetaData, String, Table, Text


def define_tables(meta):
    services = Table(
        'services', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', Integer, primary_key=True, nullable=False),
        Column('host', String(length=255)),
        Column('binary', String(length=255)),
        Column('topic', String(length=255)),
        Column('report_count', Integer, nullable=False),
        Column('disabled', Boolean),
        Column('disabled_reason', String(length=255)),
        Column('availability_zone', String(255)),
        Column('modified_at', DateTime),
        Column('rpc_current_version', String(36)),
        Column('rpc_available_version', String(36)),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    replications = Table(
        "replications", meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(36), primary_key=True, nullable=False),
        Column('user_id', String(36)),
        Column('project_id', String(36)),
        Column('host', String(length=255)),
        Column('status', String(64)),
        Column('display_name', String(255)),
        Column('display_description', String(255)),
        Column('master_volume', String(36)),
        Column('slave_volume', String(36)),
        Column('force', Boolean),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    checkpoints = Table(
        "checkpoints", meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(36), primary_key=True, nullable=False),
        Column('user_id', String(36)),
        Column('project_id', String(36)),
        Column('host', String(length=255)),
        Column('status', String(64)),
        Column('display_name', String(255)),
        Column('display_description', String(255)),
        Column('replication_id', String(36), ForeignKey('replications.id'),
               nullable=False),
        Column('master_snapshot', String(36), nullable=True),
        Column('slave_snapshot', String(36), nullable=True),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    volumes = Table(
        'volumes', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(36), primary_key=True, nullable=False),
        Column('user_id', String(36)),
        Column('project_id', String(36)),
        Column('host', String(length=255)),
        Column('status', String(64)),
        Column('previous_status', String(64)),
        Column('display_name', String(255)),
        Column('display_description', String(255)),
        Column('size', Integer),
        Column('availability_zone', String(255)),
        Column('replication_zone', String(255)),
        Column('replication_id', String(36), nullable=True),
        Column('peer_volume', String(36), nullable=True),
        Column('replicate_status', String(64)),
        Column('replicate_mode', String(64)),
        Column('access_mode', String(64)),
        Column('driver_data', Text, nullable=True),
        Column('snapshot_id', String(36), nullable=True),
        Column('sg_client', Text, nullable=True),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    snapshots = Table(
        "snapshots", meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(36), primary_key=True, nullable=False),
        Column('user_id', String(36)),
        Column('project_id', String(36)),
        Column('host', String(length=255)),
        Column('status', String(64)),
        Column('display_name', String(255)),
        Column('display_description', String(255)),
        Column('checkpoint_id', String(36), nullable=True),
        Column('destination', String(64)),
        Column('availability_zone', String(255)),
        Column('replication_zone', String(255)),
        Column('volume_id', String(36), ForeignKey('volumes.id'),
               nullable=False),
        Column('volume_size', Integer),
        Column('sg_client', Text, nullable=True),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    backups = Table(
        "backups", meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(36), primary_key=True, nullable=False),
        Column('user_id', String(36)),
        Column('project_id', String(36)),
        Column('host', String(length=255)),
        Column('status', String(64)),
        Column('display_name', String(255)),
        Column('display_description', String(255)),
        Column('size', Integer),
        Column('type', String(64)),
        Column('destination', String(64)),
        Column('availability_zone', String(255)),
        Column('replication_zone', String(255)),
        Column('volume_id', String(36), nullable=True),
        Column('driver_data', Text, nullable=True),
        Column('parent_id', String(36), nullable=True),
        Column('num_dependent_backups', Integer, default=0),
        Column('data_timestamp', DateTime),
        Column('restore_volume_id', String(36), nullable=True),
        Column('sg_client', Text, nullable=True),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    volume_attachment = Table(
        "volume_attachment", meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', String(36), primary_key=True, nullable=False),
        Column('volume_id', String(36), ForeignKey('volumes.id'),
               nullable=False),
        Column('instance_uuid', String(36)),
        Column('instance_host', String(255)),
        Column('mountpoint', String(255)),
        Column('attach_time', DateTime),
        Column('detach_time', DateTime),
        Column('attach_status', String(255)),
        Column('attach_mode', String(36)),
        Column('logical_instance_id', String(36)),

        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    volume_metadata = Table(
        'volume_metadata', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', Integer, primary_key=True, nullable=False),
        Column('volume_id', String(36), ForeignKey('volumes.id'),
               nullable=False),
        Column('key', String(255)),
        Column('value', String(255)),
        mysql_engine='InnoDB',
        mysql_charset='utf8'
    )

    return [services,
            replications,
            checkpoints,
            volumes,
            snapshots,
            backups,
            volume_attachment,
            volume_metadata]


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    # create all tables
    # Take care on create order for those with FK dependencies
    tables = define_tables(meta)

    for table in tables:
        table.create()

    if migrate_engine.name == "mysql":
        table_names = [t.description for t in tables]
        table_names.append("migrate_version")

        migrate_engine.execute("SET foreign_key_checks = 0")
        for table in table_names:
            migrate_engine.execute(
                "ALTER TABLE %s CONVERT TO CHARACTER SET utf8" % table)
        migrate_engine.execute("SET foreign_key_checks = 1")
        migrate_engine.execute(
            "ALTER DATABASE %s DEFAULT CHARACTER SET utf8" %
            migrate_engine.url.database)
        migrate_engine.execute("ALTER TABLE %s Engine=InnoDB" % table)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = define_tables(meta)
    tables.reverse()
    for table in tables:
        table.drop()
