# Copyright 2011 OpenStack Foundation
#
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

from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_utils import excutils
from oslo_utils import uuidutils
from oslo_service import loopingcall
from cinderclient.v2 import client as cinder_client
from keystoneclient.v2_0 import client as kc
from cinderclient import exceptions as cinder_exception
from keystoneclient import exceptions as keystone_exception

from sgsclient.exceptions import NotFound
from sgservice.i18n import _, _LI, _LE
from sgservice.controller.api import API as ServiceAPI
from sgservice import exception
from sgservice import objects
from sgservice.objects import fields
from sgservice import manager
from sgservice import utils
from sgservice import context

proxy_manager_opts = [
    cfg.IntOpt('sync_interval',
               default=5,
               help='seconds between cascading and cascaded sgservices when '
                    'synchronizing data'),
    cfg.IntOpt('status_query_count',
               default=5,
               help='status query times'),
    cfg.StrOpt('sgservice_username',
               default='sgservice_username',
               help='username for connecting to cinder in admin context'),
    cfg.StrOpt('admin_password',
               default='admin_password',
               help='password for connecting to cinder in admin context'),
    cfg.StrOpt('sgservice_tenant_name',
               default='sgservice_tenant_name',
               help='tenant name for connecting to cinder in admin context'),
    cfg.StrOpt('sgservice_tenant_id',
               default='sgservice_tenant_id',
               help='tenant id for connecting to cinder in admin context'),
    cfg.StrOpt('cascaded_availability_zone',
               default='nova',
               help='availability zone for cascaded OpenStack'),
    cfg.StrOpt('keystone_auth_url',
               default='http://127.0.0.1:5000/v2.0/',
               help='value of keystone url'),
    cfg.StrOpt('cascading_sgservice_url',
               default='http://127.0.0.1:8975/v1/%(project_id)s',
               help='value of cascading sgservice url'),
    cfg.StrOpt('casacaded_cinder_url',
               default='http://127.0.0.1:8776/v2/%(project_id)s',
               help='value of cascaded cinder url'),
    cfg.StrOpt('cascaded_region_name',
               default='RegionOne',
               help='Region name of this node')
    cfg.IntOpt('sync_status_interval',
               default=60,
               help='sync resources status interval')
]

CONF = cfg.CONF
LOG = logging.getLogger(__name__)
CONF.register_opts(proxy_manager_opts)


class SGServiceProxy(manager.Manager):
    RPC_API_VERSION = '1.0'
    target = messaging.Target(version=RPC_API_VERSION)

    def __init__(self, service_name=None, *args, **kwargs):
        super(SGServiceProxy, self).__init__(*args, **kwargs)
        self.service_api = ServiceAPI()
        self.adminCinderClient = self._get_cascaded_cinder_client()
        self.adminSGSClient = self._get_cascaded_sgs_client()

        self.volumes_mapping_cache = {}
        self.backups_mapping_cache = {}
        self.snapshots_mapping_cache = {}
        self.replications_mapping_cache = {}

        self.sync_status_interval = CONF.sync_status_interval
        self.sync_volumes = {}
        sync_volumes_loop = loopingcall.FixedIntervalLoopingCall(
                self._sync_volumes_status)
        sync_volumes_loop.start(interval=self.sync_status_interval,
                                      initial_delay=self.sync_status_interval)

        self.sync_backups = {}
        sync_backups_loop = loopingcall.FixedIntervalLoopingCall(
                self._sync_backups_status)
        sync_backups_loop.start(interval=self.sync_status_interval,
                                      initial_delay=self.sync_status_interval)

        self.sync_snapshots = {}
        sync_snapshots_loop = loopingcall.FixedIntervalLoopingCall(
                self._sync_snapshots_status)
        sync_snapshots_loop.start(interval=self.sync_status_interval,
                                      initial_delay=self.sync_status_interval)

        self.sync_replications = {}
        sync_replications_loop = loopingcall.FixedIntervalLoopingCall(
                self._sync_replications_status)
        sync_replications_loop.start(interval=self.sync_status_interval,
                                      initial_delay=self.sync_status_interval)

    def init_host(self, **kwargs):
        """ list all ing-status objects(volumes, snapshot, backups);
            add to self.volumes_mapping_cache, backups_mapping_cache, snapshots_mapping_cache,
            and replicates_mapping;
            start looping call to sync volumes, backups, snapshots,
            and replicates status;
        """
        # TODO(luobin)
        cxt = context.get_admin_context()
        volumes = objects.VolumeList.get_all(cxt)
        for volume in volumes:
            if volume.status in (fields.VolumeStatus.ENABLING,
                                 fields.VolumeStatus.DISABLING,
                                 fields.VolumeStatus.RESTORING_BACKUP):
                self.sync_volumes[volume.id] = volume

        snapshots = objects.SnapshotList.get_all(cxt)
        for snapshot in snapshots:
            if snapshot.status in (fields.SnapshotStatus.CREATING,
                                   fields.SnapshotStatus.DELETING):
                self.sync_snapshots[snapshot.id] = snapshot

        backups = objects.BackupList.get_all(cxt)
        for backup in backups:
            if backup.status in (fields.BackupStatus.CREATING,
                                   fields.BackupStatus,
                                 fields.BackupStatus.RESTORING):
                self.sync_backups[backup.id] = backup

        replications = objects.ReplicationList.get_all(cxt)
        for replication in replications:
             if replication.status in (fields.ReplicateStatus.ENABLING,
                                           fields.ReplicationStatus.DISABLING,
                                           fields.ReplicationStatus.DELETING,
                                           fields.ReplicationStatus.FAILING_OVER,
                                           fields.ReplicationStatus.REVERSING):
                 self.sync_replications[replication.id] = replication

    def _sync_volumes_status(self):
        """ sync cascaded volumes'(in volumes_mapping_cache) status;
            and update cascading volumes' status
        """
        for volume_id, volume in self.sync_volumes.items():
            csd_volume_id = self._get_csd_volume_id(volume_id)
            try:
                csd_volume = self.adminSGSClient.volumes.get(csd_volume_id)
            except Exception as exc:
                if type(exc) == NotFound:
                    LOG.info(_LI("disabling volume %s finished "), volume_id)
                    volume.destroy()
                    self.volumes_mapping_cache.pop(volume_id)
                    self.sync_volumes.pop(volume_id)
                continue

            if csd_volume.status == fields.VolumeStatus.ENABLING \
                    or csd_volume.status == fields.VolumeStatus.DISABLING:
                continue
            else:
                volume.update({'status': csd_volume.status})
                volume.save()
                self.sync_volumes.pop(volume_id)

    def _sync_backups_status(self):
        """ sync cascaded backups'(in volumes_mapping_cache) status;
            update cascading backups' status
        """
        for backup_id, backup in self.sync_backups.items():
            csd_backup_id = self._get_csd_backup_id(backup_id)
            try:
                csd_backup = self.adminSGSClient.backups.get(csd_backup_id)
            except Exception as exc:
                if type(exc) == NotFound:
                    LOG.info(_LI("disabling volume %s finished "), backup_id)
                    backup.destroy()
                    self.backups_mapping_cache.pop(backup_id)
                    self.sync_backups.pop(backup_id)
                continue

            if csd_backup.status in (fields.BackupStatus.CREATING,
                                     fields.BackupStatus.DELETING,
                                     fields.BackupStatus.RESTORING):
                continue
            else:
                backup.update({'status': csd_backup.status})
                backup.save()
                self.sync_backups.pop(backup_id)

    def _sync_snapshots_status(self):
        """ sync cascaded snapshots'(in volumes_mapping_cache) status;
            update cascading snapshots' status;
            # TODO update cascading checkpoints' status if needed;
        """
        for snapshot_id, snapshot in self.sync_snapshots.items():
            csd_snapshot_id = self._get_csd_snapshotp_id(snapshot_id)
            try:
                csd_snapshot = self.adminSGSClient.volumes.get(csd_snapshot_id)
            except Exception as exc:
                if type(exc) == NotFound:
                    LOG.info(_LI("disabling volume %s finished "), snapshot_id)
                    snapshot.destroy()
                    self.snapshots_mapping_cache.pop(snapshot_id)
                    self.sync_snapshots.pop(snapshot_id)
                continue

            if csd_snapshot.status in (fields.SnapshotStatus.CREATING,
                                       fields.SnapshotStatus.DELETING):
                continue
            else:
                snapshot.update({'status': csd_snapshot.status})
                snapshot.save()
                self.sync_backups.pop(snapshot_id)

    def _sync_replications_status(self):
        """ sync cascaded volumes'(in volumes_mapping_cache) replicate-status;
            update cascading volumes' replicate-status;
            update cascading replications' status;
        """
        for replication_id, replication in self.sync_replications.items():
            master_volume_id = replication['master_volume']
            slave_volume_id = replication['slave_volume']
            csd_master_volume_id = self._get_csd_volume_id(master_volume_id)
            csd_slave_volume_id = self._get_csd_volume_id(slave_volume_id)
            try:
                csd_master_volume = self.adminSGSClient.volumes.get(csd_master_volume_id)
                csd_slave_volume = self.adminSGSClient.volumes.get(csd_slave_volume_id)
            except Exception as exc:
                if type(exc) == NotFound:
                    LOG.info(_LI("delete replication %s finished "), replication_id)
                    replication.destroy()
                    self.volumes_mapping_cache.pop(master_volume_id)
                    self.volumes_mapping_cache.pop(slave_volume_id)
                    self.sync_replications.pop(replication_id)
                continue

            if csd_master_volume.replicate_status in (fields.ReplicateStatus.ENABLING,
                                               fields.ReplicateStatus.DISABLING,
                                               fields.ReplicateStatus.DELETING,
                                               fields.ReplicateStatus.FAILING_OVER,
                                               fields.ReplicateStatus.REVERSING):
                continue
            if csd_slave_volume.replicate_status in (fields.ReplicateStatus.ENABLING,
                                               fields.ReplicateStatus.DISABLING,
                                               fields.ReplicateStatus.DELETING,
                                               fields.ReplicateStatus.FAILING_OVER,
                                               fields.ReplicateStatus.REVERSING):
                continue
            else:
                master_volume = objects.Volume.get_by_id(master_volume_id)
                slave_volume = objects.Volume.get_by_id(slave_volume_id)
                master_volume.update({'replicate_status': csd_master_volume.replicate_status})
                master_volume.save()
                slave_volume.update({'replicate_status': csd_slave_volume.replicate_status})
                slave_volume.save()
                if master_volume.replicate_status == slave_volume.replicate_status:
                    replication.update({'status': master_volume.replicate_status})
                    self.sync_replications.pop(replication_id)

    def _get_cascaded_sgs_client(self, context=None):
        # TODO(luobin): get cascaded sgs client
        if context is None:
            # use use_name and password to get admin sgs client
            return
        else:
            return

    def _get_cascaded_cinder_client(self, context=None, retries=None):
        try:
            if context is None:
                cinderclient = cinder_client.Client(
                        auth_url=CONF.keystone_auth_url,
                        region_name=CONF.cascaded_region_name,
                        tenant_id=self.tenant_id,
                        api_key=CONF.admin_password,
                        username=CONF.cinder_username,
                        insecure=True,
                        timeout=120,
                        retries=retries)
            else:
                ctx_dict = context.to_dict()

                if not self._url:
                    kwargs = {
                        'auth_url': CONF.keystone_auth_url,
                        'tenant_name': CONF.cinder_tenant_name,
                        'username': CONF.cinder_username,
                        'password': CONF.admin_password,
                        'insecure': True
                    }
                    keystoneclient = kc.Client(**kwargs)
                    management_url = self._get_management_url(keystoneclient, service_type='volumev2',
                                                              attr='region',
                                                              endpoint_type='publicURL',
                                                              filter_value=CONF.cascaded_region_name)
                    self._url = management_url.rpartition("/")[0]

                LOG.info("before replace: self._url: %s", self._url)
                management_url = self._url + '/' + ctx_dict.get("project_id")
                LOG.info("after replace: management_url:%s", management_url)

                cinderclient = cinder_client.Client(
                        username=ctx_dict.get('user_id'),
                        auth_url=cfg.CONF.keystone_auth_url,
                        insecure=True,
                        timeout=120,
                        retries=retries)
                cinderclient.client.auth_token = ctx_dict.get('auth_token')
                cinderclient.client.management_url = management_url

            LOG.info(_("cascade info: os_region_name:%s"), CONF.cascaded_region_name)
            return cinderclient
        except keystone_exception.Unauthorized:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Token unauthorized failed for keystoneclient '
                            'constructed when get cascaded admin client'))
        except cinder_exception.Unauthorized:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Token unauthorized failed for cascaded '
                            'cinderClient constructed'))
        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.error(_('Failed to get cinder python client.'))

    def _gen_csd_volume_name(self, csg_volume_id):
        return 'volume@%s' % csg_volume_id

    def _get_csd_volume_id(self, volume_id):
        # get csd_volume_id from cache mapping as first
        if volume_id in self.volumes_mapping_cache.keys():
            return self.volumes_mapping_cache[volume_id]

        csd_volume_name = self._gen_csd_volume_name(volume_id)
        search_opts = {'all_tenants': True,
                       'name': csd_volume_name}
        try:
            vols = self.adminCinderClient.volumes.list(
                    search_opts=search_opts, detailed=True)
            if vols:
                csd_volume_id = vols[0]._info['id']
                self.volumes_mapping_cache[volume_id] = csd_volume_id
                return csd_volume_id
        except Exception as err:
            LOG.info(_LE("get cascaded volume id of %s err"), volume_id)
            raise err

    def enable_sg(self, context, volume_id):
        LOG.info(_LI("Enable-SG for this volume with id %s"), volume_id)
        try:
            volume = objects.Volume.get_by_id(context, volume_id)
            # step 1: get cascaded volume_id
            csd_volume_id = self._get_csd_volume_id(volume_id)

            # step 2: enable sg in cascaded
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            csd_sgs_client.volumes.enable_sg(csd_volume_id)
            # step 3: add to sync status map
            self.volumes_mapping_cache[volume_id] = csd_volume_id
            self.sync_volumes[volume_id] = volume
        except Exception:
            LOG.info(_LE("enable sg volume=%s error"), volume_id)
            volume.update({'status': fields.VolumeStatus.ERROR})
            volume.save()

    def disable_sg(self, context, volume_id):
        try:
            volume = objects.Volume.get_by_id(context, volume_id)
            # step 1: get cascaded volume_id
            csd_volume_id = self._get_csd_volume_id(volume_id)

            # step 2: enable sg in cascaded
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            csd_sgs_client.volumes.disable_sg(csd_volume_id)
            # step 3: add to sync status map
            self.volumes_mapping_cache[volume_id] = csd_volume_id
            self.sync_volumes[volume_id] = volume
        except Exception as err:
            LOG.info(_LE("disable sg volume=%s error"), volume_id)
            volume.update({'status': fields.VolumeStatus.ERROR})
            volume.save()

    def attach_volume(self, context, volume_id, instance_uuid, host_name,
                      mountpoint, mode):
        """cascaded attach_volume will be called in nova-proxy
           sgservice-proxy just update cascading level data
        """
        volume = objects.Volume.get_by_id(context, volume_id)
        if volume['status'] == fields.VolumeStatus.ATTACHING:
            access_mode = volume['access_mode']
            if access_mode is not None and access_mode != mode:
                raise exception.InvalidVolume(
                        reason=_('being attached by different mode'))

        host_name_sanitized = utils.sanitize_hostname(
                host_name) if host_name else None
        if instance_uuid:
            attachments = self.db.volume_attachment_get_all_by_instance_uuid(
                    context, volume_id, instance_uuid)
        else:
            attachments = self.db.volume_attachment_get_all_by_host(
                    context, volume_id, host_name_sanitized)
        if attachments:
            volume.update({'status': fields.VolumeStatus.IN_USE})
            volume.save()
            return

        values = {'volume_id': volume_id,
                  'attach_status': fields.VolumeStatus.ATTACHING}
        attachment = self.db.volume_attach(context.elevated(), values)
        attachment_id = attachment['id']

        if instance_uuid and not uuidutils.is_uuid_like(instance_uuid):
            self.db.volume_attachment_update(
                    context, attachment_id, {'attach_status': fields.VolumeStatus.ERROR_ATTACHING})
            raise exception.InvalidUUID(uuid=instance_uuid)

        self.db.volume_attached(context.elevated(),
                                attachment_id,
                                instance_uuid,
                                host_name_sanitized,
                                mountpoint,
                                mode)
        LOG.info(_LI("Attach volume completed successfully."))

    def initialize_connection(self, context, volume_id, connector):
        # just need return None
        return None

    def _gen_csd_backup_name(self, backup_id):
        return 'backup@%s' % backup_id

    def _get_csd_backup_id(self, backup_id):
        # get csd_backup_id from cache mapping as first
        if backup_id in self.backups_mapping_cache.keys():
            return self.backups_mapping_cache[backup_id]
        csd_backup_name = self._gen_csd_backup_name(backup_id)
        search_opts = {'all_tenants': True,
                       'name': csd_backup_name}
        try:
            backups = self.adminSGSClient.backups.list(
                    search_opts=search_opts)
            if backups:
                csd_backup_id = backups[0]._info['id']
                self.backups_mapping_cache[backup_id] = csd_backup_id
                return csd_backup_id
        except Exception as err:
            raise err

    def _update_backup_error(self, backup):
        backup.update({'status': fields.BackupStatus.ERROR})
        backup.save()

    def create_backup(self, context, backup_id):
        # step 1: check status in cascading level
        backup = objects.Backup.get_by_id(context, backup_id)
        volume_id = backup.volume_id
        LOG.info(_LI("Create backup started, backup:%(backup_id)s, volume: "
                     "%(volume_id)s"),
                 {'volume_id': volume_id, 'backup_id': backup_id})

        volume = objects.Volume.get_by_id(context, volume_id)
        previous_status = volume.get('previous-status', None)

        expected_status = 'backing-up'
        actual_status = volume['status']
        if actual_status != expected_status:
            msg = (_('Create backup aborted, expected volume status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self._update_backup_error(backup)
            self.db.volume_update(context, volume_id,
                                  {'status': previous_status,
                                   'previous_status': 'error_backing_up'})
            raise exception.InvalidVolume(reason=msg)

        expected_status = fields.BackupStatus.CREATING
        actual_status = backup['status']
        if actual_status != expected_status:
            msg = (_('Create backup aborted, expected backup status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self._update_backup_error(backup)
            self.db.volume_update(context, volume_id,
                                  {'status': previous_status,
                                   'previous_status': 'error_backing_up'})
            raise exception.InvalidBackup(reason=msg)

        try:
            # step 2: call create backup to cascaded level
            csd_volume_id = self._get_csd_volume_id(volume_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            display_name = "backup@%s" % backup_id
            csd_backup = csd_sgs_client.backups.create(
                    volume_id=csd_volume_id,
                    type=backup['type'],
                    destination=backup['destination'],
                    name=display_name)

            # step 3: add to sync status map
            self.backups_mapping_cache[backup_id] = csd_backup['id']
            self.sync_backups[backup_id] = backup
        except Exception:
            with excutils.save_and_reraise_exception():
                self._update_backup_error(backup)
                self.db.volume_update(context, volume_id,
                                      {'status': previous_status,
                                       'previous_status': 'error_backing_up'})

    def delete_backup(self, context, backup_id):
        # step 1: check status in cascading level
        backup = objects.Backup.get_by_id(context, backup_id)

        expected_status = fields.BackupStatus.DELETING
        actual_status = backup['status']
        if actual_status != expected_status:
            msg = (_('Delete backup aborted, expected backup status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self._update_backup_error(backup)
            raise exception.InvalidBackup(reason=msg)

        try:
            # step 2: call delete backup to cascaded level
            csd_backup_id = self._get_csd_backup_id(backup_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            csd_sgs_client.backups.delete(csd_backup_id)

            # step 3: add to sync status
            self.backups_mapping_cache[backup_id] = csd_backup_id
            self.sync_backups[backup_id] = backup
        except Exception:
            with excutils.save_and_reraise_exception():
                self._update_backup_error(backup)

    def restore_backup(self, context, backup_id, volume_id):
        # step 1: check status in cascading level
        volume = objects.Volume.get_by_id(context, volume_id)
        backup = objects.Backup.get_by_id(context, backup_id)

        expected_status = 'restoring-backup'
        actual_status = volume['status']
        if actual_status != expected_status:
            msg = (_('Restore backup aborted, expected volume status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self.db.backup_update(
                    context, backup_id,
                    {'status': fields.BackupStatus.AVAILABLE})
            self.db.volume_update(
                    context, volume_id,
                    {'status': fields.VolumeStatus.ERROR_RESTORING})
            raise exception.InvalidVolume(reason=msg)

        expected_status = 'restoring'
        actual_status = volume['status']
        if actual_status != expected_status:
            msg = (_('Restore backup aborted, expected volume status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self._update_backup_error(backup)
            self.db.volume_update(context, volume_id,
                                  {'status': fields.VolumeStatus.ERROR})
            raise exception.InvalidVolume(reason=msg)

        try:
            # step 2: call restore backup to cascaded level
            csd_volume_id = self._get_csd_volume_id(volume_id)
            csd_backup_id = self._get_csd_backup_id(backup_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            csd_sgs_client.backups.restore(backup_id=csd_backup_id,
                                           volume_id=csd_volume_id)

            # step 3: add to sync status
            self.backups_mapping_cache[backup_id] = csd_backup_id
            self.volumes_mapping_cache[volume_id] = csd_volume_id
            self.sync_backups[backup_id] = backup
            self.sync_volumes[volume_id] = volume
        except Exception:
            with excutils.save_and_reraise_exception():
                self.db.backup_update(
                        context, backup_id,
                        {'status': fields.BackupStatus.AVAILABLE})
                self.db.volume_update(
                        context, volume_id,
                        {'status': fields.VolumeStatus.ERROR_RESTORING})

    def _update_snapshot_error(self, snapshot):
        snapshot.update({'status': fields.SnapshotStatus.ERROR})
        snapshot.save()

    def _update_replication_error(self, volume, replication):
        volume.update({'replicate_status': fields.ReplicateStatus.ERROR})
        volume.save()
        peer_volume_id = volume['peer_volume']
        peer_volume = objects.Volume.get_by_id(context, peer_volume_id)
        peer_volume.update({'replicate_status': fields.ReplicateStatus.ERROR})
        peer_volume.save()
        replication.update({'status': fields.ReplicationStatus.ERROR})
        replication.save()

    def _gen_csd_snapshot_name(self, snapshot_id):
        return 'snapshot@%s' % snapshot_id

    def _get_csd_snapshot_id(self, snapshot_id):
        # get csd_snapshot_id from cache mapping as first
        if snapshot_id in self.snapshots_mapping_cache.keys():
            return self.snapshots_mapping_cache[snapshot_id]

        csd_snapshot_name = self._gen_csd_snapshot_name(snapshot_id)
        search_opts = {'all_tenants': True,
                       'name': csd_snapshot_name}
        try:
            snapshots = self.adminSGSClient.snapshots.list(
                    search_opts=search_opts)
            if snapshots:
                csd_snapshot_id = snapshots[0]._info['id']
                self.snapshots_mapping_cache[snapshot_id] = csd_snapshot_id
                return csd_snapshot_id
        except Exception as err:
            raise err

    def create_snapshot(self, context, snapshot_id):
        # step 1: check status in cascading level
        snapshot = objects.Snapshot.get_by_id(context, snapshot_id)
        volume_id = snapshot.volume_id
        objects.Volume.get_by_id(context, volume_id)

        expected_status = fields.SnapshotStatus.CREATING
        actual_status = snapshot['status']
        if actual_status != expected_status:
            msg = (_('Create snapshot aborted, expected snapshot status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self._update_snapshot_error(snapshot)
            raise exception.InvalidSnapshot(reason=msg)

        try:
            # step 2: call create snapshot to cascaded level
            csd_volume_id = self._get_csd_volume_id(volume_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            display_name = self._gen_csd_snapshot_name(snapshot_id)
            csd_snapshot = csd_sgs_client.snapshots.create(
                    volume_id=csd_volume_id,
                    name=display_name,
                    checkpoint_id=snapshot['checkpoint-id'])

            # step 3: add to sync status
            self.sync_snapshots[snapshot_id] = snapshot
        except Exception:
            with excutils.save_and_reraise_exception():
                self._update_snapshot_error(snapshot)

    def delete_snapshot(self, context, snapshot_id):
        # step 1: check status in cascading level
        snapshot = objects.Snapshot.get_by_id(context, snapshot_id)

        expected_status = fields.SnapshotStatus.DELETING
        actual_status = snapshot['status']
        if actual_status != expected_status:
            msg = (_('Delete snapshot aborted, expected backup status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self._update_snapshot_error(snapshot)
            raise exception.InvalidBackup(reason=msg)

        try:
            # step 2: call delete snapshot to cascaded level
            csd_snapshot_id = self._get_csd_snapshot_id(snapshot_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            csd_sgs_client.snapshots.delete(snapshot_id=csd_snapshot_id)

            # step 3: add to sync status
            self.snapshots_mapping_cache[snapshot_id] = csd_snapshot_id
            self.sync_snapshots[snapshot_id] = snapshot
        except Exception:
            with excutils.save_and_reraise_exception():
                self._update_snapshot_error(snapshot)

    def create_replicate(self, context, volume_id):
        # step 1: check status in cascading level
        volume = objects.Volume.get_by_id(context, volume_id)

        expected_status = fields.ReplicateStatus.ENABLING
        actual_status = volume['replicate_status']
        if actual_status != expected_status:
            msg = (_('Create replicate aborted, expected replicate status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self.db.volume_update(
                    context, volume_id,
                    {'replicate_status': fields.ReplicateStatus.ERROR})
            raise exception.InvalidVolume(reason=msg)

        try:
            # step 2: call create replicate to cascaded level
            csd_volume_id = self._get_csd_volume_id(volume_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            mode = volume['replicate_mode']
            peer_volume_id = volume['peer_volume']
            csd_peer_volume_id = self._get_csd_volume_id(peer_volume_id)
            replication_id = volume['replication_id']
            replication = objects.Replication.get_by_id(context, replication_id)
            csd_sgs_client.replicates.create(volume_id=csd_volume_id,
                                             mode=mode,
                                             peer_volume=csd_peer_volume_id,
                                             replication_id=replication_id)

            # step 3: add to sync status map
            self.sync_replications[replication_id] = replication

        except Exception:
            with excutils.save_and_reraise_exception():
                self._update_replication_error(volume, replication)

    def delete_replicate(self, context, volume_id):
        # step 1: check status in cascading level
        volume = objects.Volume.get_by_id(context, volume_id)

        replication_id = volume['replication_id']
        replication = objects.Replication.get_by_id(context, replication_id)
        expected_status = fields.ReplicateStatus.DELETING
        actual_status = volume['replicate_status']
        if actual_status != expected_status:
            msg = (_('Delete replicate aborted, expected replicate status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self.db.volume_update(
                    context, volume_id,
                    {'replicate_status': fields.ReplicateStatus.ERROR})
            raise exception.InvalidVolume(reason=msg)

        try:
            # step 2: call delete replicate to cascaded level
            csd_volume_id = self._get_csd_volume_id(volume_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            self.driver.enable_replicate(volume=volume)
            csd_sgs_client.replicates.delete(csd_volume_id)

            # step 3: add to sync status map
            self.sync_replications[replication_id] = replication
        except Exception:
            with excutils.save_and_reraise_exception():
                self._update_replication_error(volume, replication)

    def enable_replicate(self, context, volume_id):
        # step 1: check status in cascading level
        volume = objects.Volume.get_by_id(context, volume_id)
        replication_id = volume['replication_id']
        replication = objects.Replication.get_by_id(context, replication_id)

        expected_status = fields.ReplicateStatus.ENABLING
        actual_status = volume['replicate_status']
        if actual_status != expected_status:
            msg = (_('Enable replicate aborted, expected replicate status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self.db.volume_update(
                    context, volume_id,
                    {'replicate_status': fields.ReplicateStatus.ERROR})
            raise exception.InvalidVolume(reason=msg)

        try:
            # step 2: call enable replicate to cascaded level
            csd_volume_id = self._get_csd_volume_id(volume_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            self.driver.enable_replicate(volume=volume)
            csd_sgs_client.replicates.enable(csd_volume_id)

            # step 3: add to sync status map
            self.sync_replications[replication_id] = replication
        except Exception:
            with excutils.save_and_reraise_exception():
                self._update_replication_error(volume, replication)

    def disable_replicate(self, context, volume_id):
        # step 1: check status in cascading level
        volume = objects.Volume.get_by_id(context, volume_id)
        peer_volume_id = volume['peer_volume']
        peer_volume = objects.Volume.get_by_id(context, peer_volume_id)
        replication_id = volume['replication_id']
        replication = objects.Replication.get_by_id(context, replication_id)

        expected_status = fields.ReplicateStatus.DISABLING
        actual_status = volume['replicate_status']
        if actual_status != expected_status:
            msg = (_('Disable replicate aborted, expected replicate status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self.db.volume_update(
                    context, volume_id,
                    {'replicate_status': fields.ReplicateStatus.ERROR})
            raise exception.InvalidVolume(reason=msg)

        try:
            # step 2: call disable replicate to cascaded level
            csd_volume_id = self._get_csd_volume_id(volume_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            self.driver.enable_replicate(volume=volume)
            csd_sgs_client.replicates.disable(csd_volume_id)

            # step 3: add to sync status
            self.sync_replications[replication_id] = replication
        except Exception:
            with excutils.save_and_reraise_exception():
                self._update_replication_error(volume, replication)

    def failover_replicate(self, context, volume_id):
        # step 1: check status in cascading level
        volume = objects.Volume.get_by_id(context, volume_id)
        replication_id = volume['replication_id']
        replication = objects.Replication.get_by_id(context, replication_id)
        expected_status = fields.ReplicateStatus.FAILING_OVER
        actual_status = volume['replicate_status']
        if actual_status != expected_status:
            msg = (_('Failover replicate aborted, expected replicate status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self.db.volume_update(
                    context, volume_id,
                    {'replicate_status': fields.ReplicateStatus.ERROR})
            raise exception.InvalidVolume(reason=msg)

        try:
            # step 2: call failover replicate to cascaded level
            csd_volume_id = self._get_csd_volume_id(volume_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            self.driver.enable_replicate(volume=volume)
            csd_sgs_client.replicates.failover(csd_volume_id)

            # step 3: add to sync status
            self.sync_replications[replication_id] = replication
        except Exception:
            with excutils.save_and_reraise_exception():
                self._update_replication_error(volume, replication)

    def reverse_replicate(self, context, volume_id):
        # step 1: check status in cascading level
        volume = objects.Volume.get_by_id(context, volume_id)
        replication_id = volume['replication_id']
        replication = objects.Replication.get_by_id(context, replication_id)
        expected_status = fields.ReplicateStatus.REVERSING
        actual_status = volume['replicate_status']
        if actual_status != expected_status:
            msg = (_('Reverse replicate aborted, expected replicate status '
                     '%(expected_status)% but got %(actual_status)s')
                   % {'expected_status': expected_status,
                      'actual_status': actual_status})
            self._update_replication_error(volume, replication)
            raise exception.InvalidVolume(reason=msg)

        try:
            # step 2: call reverse replicate to cascaded level
            csd_volume_id = self._get_csd_volume_id(volume_id)
            csd_sgs_client = self._get_cascaded_sgs_client(context)
            self.driver.enable_replicate(volume=volume)
            csd_sgs_client.replicates.reverse(csd_volume_id)

            # step 3: add to sync status
            self.sync_replications[replication_id] = replication
        except Exception:
            with excutils.save_and_reraise_exception():
                self._update_replication_error(volume, replication)