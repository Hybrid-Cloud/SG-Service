from wormhole import wsgi
#from wormhole import container
from wormhole import host
from wormhole import volumes
from wormhole import sgagents
from wormhole import tasks


class Router(wsgi.ComposableRouter):
    def add_routes(self, mapper):
        for r in [host, volumes, sgagents, tasks]:
            r.create_router(mapper)
