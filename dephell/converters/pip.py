# built-in
from urllib.parse import urlparse

# external
from pip._internal.download import PipSession
from pip._internal.index import PackageFinder
from pip._internal.req import parse_requirements

# app
from ..config import config
from ..models import Dependency, RootDependency
from ..repositories import WareHouseRepo
from .base import BaseConverter


class PIPConverter(BaseConverter):
    sep = ' \\\n  '

    def __init__(self, lock):
        self.lock = lock

    def load(self, path) -> RootDependency:
        deps = []
        root = RootDependency(raw_name=self._get_name(path=path))

        warehouse_url = urlparse(config['warehouse']).hostname
        if warehouse_url in ('pypi.org', 'pypi.python.org'):
            warehouse_url += '/simple'

        finder = PackageFinder(
            find_links=[],
            index_urls=[warehouse_url],
            session=PipSession(),
        )
        # https://github.com/pypa/pip/blob/master/src/pip/_internal/req/constructors.py
        reqs = parse_requirements(
            filename=str(path),
            session=PipSession(),
            finder=finder,
        )

        for req in reqs:
            # https://github.com/pypa/pip/blob/master/src/pip/_internal/req/req_install.py
            deps.append(Dependency.from_requirement(
                source=root,
                req=req.req,
                url=req.link and req.link.url,
                editable=req.editable,
            ))

        # update repository
        if finder.index_urls:
            finded_host = urlparse(finder.index_urls[0]).hostname
            if finded_host != urlparse(warehouse_url).hostname:
                repo = WareHouseRepo(url=finder.index_urls[0])
                for dep in deps:
                    if isinstance(dep.repo, WareHouseRepo):
                        dep.repo = repo

        root.attach_dependencies(deps)
        return root

    def dumps(self, reqs, project: RootDependency, content=None) -> str:
        lines = []

        # get repos urls
        urls = dict()
        for req in reqs:
            if isinstance(req.dep.repo, WareHouseRepo):
                urls[req.dep.repo.name] = req.dep.repo.url

        # dump repos urls
        # pip._internal.build_env
        if len(urls) == 1:
            _name, url = urls.popitem()
        elif 'pypi' in urls:
            url = urls.pop('pypi')
        else:
            url = None
        if url:
            lines.append('-i ' + url)
        for url in urls.values():
            lines.append('--extra-index-url ' + url)

        for req in reqs:
            lines.append(self._format_req(req=req))
        return '\n'.join(lines) + '\n'

    # https://github.com/pypa/packaging/blob/master/packaging/requirements.py
    # https://github.com/jazzband/pip-tools/blob/master/piptools/utils.py
    def _format_req(self, req):
        line = ''
        if req.editable:
            line += '-e '
        if req.link is not None:
            line += req.link.long
        else:
            line += req.name
        if req.extras:
            line += '[{extras}]'.format(extras=','.join(req.extras))
        if req.version:
            line += req.version
        if req.markers:
            line += '; ' + req.markers
        if req.hashes:
            for digest in req.hashes:
                # https://github.com/jazzband/pip-tools/blob/master/piptools/writer.py
                line += '{sep}--hash sha256:{hash}'.format(
                    sep=self.sep,
                    hash=digest,
                )
        if req.sources:
            line += '{sep}# ^ from {sources}'.format(
                sep=self.sep,
                sources=', '.join(req.sources),
            )
        return line