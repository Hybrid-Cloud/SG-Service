#    Copyright 2015 IBM Corp.
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

"""Custom fields for Cinder objects."""

from oslo_versionedobjects import fields

BaseEnumField = fields.BaseEnumField
Enum = fields.Enum
Field = fields.Field
FieldType = fields.FieldType


class BaseSGServiceEnum(Enum):
    def __init__(self):
        super(BaseSGServiceEnum, self).__init__(
            valid_values=self.__class__.ALL)


class VolumeStatus(BaseSGServiceEnum):
    ERROR = 'error'
    ENABLING = 'enabling'
    ENABLED = 'enabled'
    DELETING = 'deleting'
    DELETED = 'deleted'
    DISABLING = 'disabling'
    DISABLED = 'disabled'
    ATTACHING = 'attaching'
    DETACHING = 'detaching'
    IN_USE = 'in-use'
    RESTORING_BACKUP = 'restoring_backup'
    ERROR_RESTORING = 'error_restoring'
    ERROR_ATTACHING = 'error_attaching'
    ERROR_DETACHING = 'error_detaching'
    ROLLING_BACK = 'rolling_back'
    BACKING_UP = 'backing-up'
    CREATING = 'creating'
    AVAILABLE = 'available'

    ALL = (ERROR, ENABLING, ENABLED, DELETING, DELETED, DISABLING, DISABLED,
           RESTORING_BACKUP, ERROR_RESTORING, ROLLING_BACK, BACKING_UP,
           ATTACHING, DETACHING, IN_USE, ERROR_ATTACHING, ERROR_DETACHING,
           CREATING, AVAILABLE)


class VolumeStatusField(BaseEnumField):
    AUTO_TYPE = VolumeStatus()


class ReplicationStatus(BaseSGServiceEnum):
    ERROR = 'error'
    ENABLING = 'enabling'
    ENABLED = 'enabled'
    DISABLING = 'disabling'
    DISABLED = 'disabled'
    DELETING = 'deleting'
    DELETED = 'deleted'
    FAILING_OVER = 'failing-over'
    FAILED_OVER = 'failed-over'
    REVERSING = 'reversing'
    CREATING = 'creating'

    ALL = (ERROR, ENABLING, ENABLED, DISABLING, DISABLED, DELETING, DELETED,
           FAILING_OVER, FAILED_OVER, REVERSING, CREATING)


class ReplicationStatusField(BaseEnumField):
    AUTO_TYPE = ReplicationStatus()


class ReplicateStatus(BaseSGServiceEnum):
    ERROR = 'error'
    ENABLING = 'enabling'
    ENABLED = 'enabled'
    DISABLING = 'disabling'
    DISABLED = 'disabled'
    DELETING = 'deleting'
    DELETED = 'deleted'
    FAILING_OVER = 'failing-over'
    FAILED_OVER = 'failed-over'
    REVERSING = 'reversing'
    CREATING = 'creating'

    ALL = (ERROR, ENABLING, ENABLED, DISABLING, DISABLED, DELETING, DELETED,
           FAILING_OVER, FAILED_OVER, REVERSING, CREATING)


class ReplicateStatusField(BaseEnumField):
    AUTO_TYPE = ReplicateStatus()


class SnapshotStatus(BaseSGServiceEnum):
    ERROR = 'error'
    AVAILABLE = 'available'
    CREATING = 'creating'
    DELETING = 'deleting'
    DELETED = 'deleted'
    ERROR_DELETING = 'error_deleting'
    ROLLING_BACK = 'rolling-back'

    ALL = (ERROR, AVAILABLE, CREATING, DELETING, DELETED,
           ERROR_DELETING, ROLLING_BACK)


class SnapshotStatusField(BaseEnumField):
    AUTO_TYPE = SnapshotStatus()


class BackupStatus(BaseSGServiceEnum):
    ERROR = 'error'
    ERROR_DELETING = 'error_deleting'
    CREATING = 'creating'
    AVAILABLE = 'available'
    DELETING = 'deleting'
    DELETED = 'deleted'
    RESTORING = 'restoring'

    ALL = (ERROR, ERROR_DELETING, CREATING, AVAILABLE, DELETING, DELETED,
           RESTORING)


class BackupStatusField(BaseEnumField):
    AUTO_TYPE = BackupStatus()


class CheckpointStatus(BaseSGServiceEnum):
    ERROR = 'error'
    CREATING = 'creating'
    AVAILABLE = 'available'
    DELETING = 'deleting'
    DELETED = 'deleted'
    ROLLING_BACK = 'rolling-back'

    ALL = (ERROR, CREATING, AVAILABLE, DELETING, DELETED, ROLLING_BACK)


class CheckpointStatusField(BaseEnumField):
    AUTO_TYPE = CheckpointStatus()


class VolumeAttachStatus(BaseSGServiceEnum):
    ATTACHED = 'attached'
    ATTACHING = 'attaching'
    DETACHED = 'detached'
    RESERVED = 'reserved'
    ERROR_ATTACHING = 'error_attaching'
    ERROR_DETACHING = 'error_detaching'
    DELETED = 'deleted'

    ALL = (ATTACHED, ATTACHING, DETACHED, ERROR_ATTACHING,
           ERROR_DETACHING, RESERVED, DELETED)


class VolumeAttachStatusField(BaseEnumField):
    AUTO_TYPE = VolumeAttachStatus()
