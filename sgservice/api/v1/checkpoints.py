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

"""The checkpoints api."""

from oslo_config import cfg
from oslo_log import log as logging
import webob
from webob import exc

from sgservice.api import common
from sgservice.api.openstack import wsgi
from sgservice.controller.api import API as ServiceAPI
from sgservice import exception
from sgservice.i18n import _, _LI
from sgservice.objects import fields
from sgservice import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

query_checkpoint_filters_opts = cfg.ListOpt(
    'query_checkpoint_filters',
    default=['name', 'status', 'replication_id'],
    help='Checkpoint filter options which non-admin user could use to query '
         'checkpoints.')
CONF.register_opt(query_checkpoint_filters_opts)


class CheckpointViewBuilder(common.ViewBuilder):
    """Model a server API response as a python dictionary."""

    _collection_name = "checkpoints"

    def __init__(self):
        """Initialize view builder."""
        super(CheckpointViewBuilder, self).__init__()

    def detail(self, request, checkpoint):
        """Detailed view of a single checkpoint."""
        checkpoint_ref = {
            'checkpoint': {
                'id': checkpoint.get('id'),
                'user_id': checkpoint.get('user_id'),
                'project_id': checkpoint.get('project_id'),
                'status': checkpoint.get('status'),
                'name': checkpoint.get('display_name'),
                'description': checkpoint.get('display_description'),
                'replication_id': checkpoint.get('replication_id'),
                'master_snapshot': checkpoint.get('master_snapshot'),
                'slave_snapshot': checkpoint.get('slave_snapshot')
            }
        }
        return checkpoint_ref

    def rollback_summary(self, request, rollback):
        """summary view of rollback"""
        rollback_ref = {
            'rollback': {
                'id': rollback.get('id'),
                'master_volume': rollback.get('master_volume'),
                'slave_volume': rollback.get('slave_volume')
            }
        }
        return rollback_ref

    def detail_list(self, request, checkpoints, checkpoint_count=None):
        """Detailed view of a list of checkpoints."""
        return self._list_view(self.detail, request, checkpoints,
                               checkpoint_count,
                               self._collection_name)

    def _list_view(self, func, request, checkpoints, checkpoint_count,
                   coll_name=_collection_name):
        """Provide a view for a list of checkpoints.

        :param func: Function used to format the checkpoint data
        :param request: API request
        :param checkpoints: List of checkpoints in dictionary format
        :param checkpoint_count: Length of the original list of checkpoints
        :param coll_name: Name of collection, used to generate the next link
                          for a pagination query
        :returns: Checkpoint data in dictionary format
        """
        checkpoints_list = [func(request, checkpoint)['checkpoint'] for
                            checkpoint in checkpoints]
        checkpoints_links = self._get_collection_links(request,
                                                       checkpoints,
                                                       coll_name,
                                                       checkpoint_count)
        checkpoints_dict = {}
        checkpoints_dict['checkpoints'] = checkpoints_list
        if checkpoints_links:
            checkpoints_dict['checkpoints_links'] = checkpoints_links

        return checkpoints_dict


class CheckpointsController(wsgi.Controller):
    """The Checkpoints API controller for the SG-Service."""

    _view_builder_class = CheckpointViewBuilder

    def __init__(self):
        self.service_api = ServiceAPI()
        super(CheckpointsController, self).__init__()

    def _get_checkpoint_filter_options(self):
        return CONF.query_checkpoint_filters

    def show(self, req, id):
        """Return data about the given checkpoints."""
        LOG.info(_LI("Show checkpoint with id: %s"), id)
        context = req.environ['sgservice.context']
        checkpoint = self.service_api.get_checkpoint(context, id)
        return self._view_builder.detail(req, checkpoint)

    def delete(self, req, id):
        """Delete a checkpoint."""
        LOG.info(_LI("Delete checkpoint with id: %s"), id)
        context = req.environ['sgservice.context']
        checkpoint = self.service_api.get_checkpoint(context, id)
        self.service_api.delete_checkpoint(context, checkpoint)
        return webob.Response(status_int=202)

    def index(self, req):
        """Returns a list of checkpoints, transformed through view builder."""
        LOG.info(_LI("Show checkpoint list"))
        context = req.environ['sgservice.context']
        params = req.params.copy()
        marker, limit, offset = common.get_pagination_params(params)
        sort_keys, sort_dirs = common.get_sort_params(params)
        filters = params

        utils.remove_invaild_filter_options(
            context, filters, self._get_checkpoint_filter_options())
        utils.check_filters(filters)

        if 'name' in sort_keys:
            sort_keys[sort_keys.index('name')] = 'display_name'

        if 'name' in filters:
            filters['display_name'] = filters.pop('name')

        checkpoints = self.service_api.get_all_checkpoints(
            context, marker=marker, limit=limit, sort_keys=sort_keys,
            sort_dirs=sort_dirs, filters=filters, offset=offset)

        retval_checkpoints = self._view_builder.detail_list(req, checkpoints)
        LOG.info(_LI("Show checkpoint list request issued successfully."))
        return retval_checkpoints

    def create(self, req, body):
        """Creates a new checkpoint."""
        if not self.is_valid_body(body, 'checkpoint'):
            raise exc.HTTPUnprocessableEntity()
        LOG.debug('Create replication request body: %s', body)
        context = req.environ['sgservice.context']
        checkpoint = body['checkpoint']

        replication_id = checkpoint.get('replication_id', None)
        if replication_id is None:
            msg = _('Incorrect request body format')
            raise webob.exc.HTTPBadRequest(explanation=msg)

        name = checkpoint.get('name', None)
        description = checkpoint.get('description', None)
        if description is None:
            description = 'checkpoint-%s' % replication_id

        replication = self.service_api.get_replication(context,
                                                       replication_id)
        checkpoint = self.service_api.create_checkpoint(context, name,
                                                        description,
                                                        replication)
        return self._view_builder.detail(req, checkpoint)

    def update(self, req, id, body):
        """Update a checkpoint."""
        LOG.info(_LI("Update checkpoint with id: %s"), id)
        context = req.environ['sgservice.context']
        if not body:
            msg = _("Missing request body")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        if 'checkpoint' not in body:
            msg = (_("Missing required element '%s' in request body"),
                   'checkpoint')
            raise webob.exc.HTTPBadRequest(explanation=msg)

        checkpoint = body['checkpoint']
        update_dict = {}

        valid_update_keys = (
            'name',
            'description',
            'display_name',
            'display_description',
        )
        for key in valid_update_keys:
            if key in checkpoint:
                update_dict[key] = checkpoint[key]
        self.validate_name_and_description(update_dict)
        if 'name' in update_dict:
            update_dict['display_name'] = update_dict.pop('name')
        if 'description' in update_dict:
            update_dict['display_description'] = update_dict.pop('description')

        checkpoint = self.service_api.get_checkpoint(context, id)
        checkpoint.update(update_dict)
        checkpoint.save()

        return self._view_builder.detail(req, checkpoint)

    @wsgi.action('rollback')
    def rollback(self, req, id, body):
        """Rollback a checkpoint"""
        LOG.info(_LI("Rollback checkpoint with id: %s"), id)
        context = req.environ['sgservice.context']
        checkpoint = self.service_api.get_checkpoint(context, id)
        rollback = self.service_api.rollback_checkpoint(context, checkpoint)
        return self._view_builder.rollback_summary(req, rollback)

    @wsgi.action('reset_status')
    def reset_status(self, req, id, body):
        """reset checkpoint status"""
        LOG.info(_LI("Reset checkpoint status, id: %s"), id)
        status = body['reset_status'].get('status',
                                          fields.CheckpointStatus.AVAILABLE)
        if status not in fields.CheckpointStatus.ALL:
            msg = _("Invalid status provided.")
            LOG.error(msg)
            raise exception.InvalidStatus(status=status)

        context = req.environ['sgservice.context']
        checkpoint = self.service_api.get_checkpoint(context, id)
        checkpoint.status = status
        checkpoint.save()
        # reset master snapshot status
        try:
            master_snapshot = self.service_api.get_snapshot(
                context, checkpoint.master_snapshot)
            master_snapshot.status = status
            master_snapshot.save()
        except Exception:
            pass
        # reset slave snapshot status
        try:
            slave_snapshot = self.service_api.get_snapshot(
                context, checkpoint.slave_snapshot)
            slave_snapshot.status = status
            slave_snapshot.save()
        except Exception:
            pass

        return webob.Response(status_int=202)


def create_resource():
    return wsgi.Resource(CheckpointsController())
