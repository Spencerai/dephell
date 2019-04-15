from datetime import datetime
from pathlib import Path
from typing import Union, Optional, Tuple

from .base import Interface
from ..constants import FILES
from ..config import Config
from ..models.release import Release


class LocalRepo(Interface):
    def __init__(self, path: Union[Path, str]):
        if type(path) is str:
            path = Path(path)
        self.path = path

    def get_releases(self, dep) -> Tuple[Release, ...]:
        releases = []
        for path in (self.path / 'dist').iterdir():
            version = path.name
            for suffix in ('.gz', '.bz', '.zip', '.tar', '.whl', '.tgz'):
                if version.endswith(suffix):
                    version = version[:-len(suffix)]
            if version.startswith(dep.name) or version.startswith(dep.name.replace('-', '_')):
                version = version[len(dep.name):]
            releases.append(Release(
                raw_name=dep.raw_name,
                version=version,
                time=datetime.fromtimestamp(path.stat().st_mtime),
            ))

        root = self.get_root(name=dep.name, version=dep.version)
        self.update_dep_from_root(dep=dep, root=root)
        releases.append(Release(
            raw_name=root.raw_name,
            version=root.version,
            time=datetime.fromtimestamp(self.path.stat().st_mtime),
        ))

        return tuple(reversed(releases))

    async def get_dependencies(self, name: str, version: str, extra: Optional[str] = None) -> tuple:
        root = self.get_root(name=name, version=version)
        deps = root.dependencies
        if extra:
            deps = tuple(dep for dep in deps if extra in dep.envs)
        return deps

    def get_root(self, name: str, version: str):
        from ..converters import EggInfoConverter, SDistConverter, WheelConverter, CONVERTERS

        if not self.path.exists():
            raise FileNotFoundError(str(self.path))

        # load from file
        if self.path.is_file():
            for converter in CONVERTERS.values():
                if converter.can_parse(path=self.path):
                    return converter.load(path=self.path)
            raise LookupError('cannot find loader for file ' + str(self.path))

        # get from wheel or sdist
        PATTERNS = (
            ('-*-*-*.whl', WheelConverter()),
            ('.tar.gz', SDistConverter()),
            ('.tgz', SDistConverter()),
        )
        for suffix, converter in PATTERNS:
            paths = tuple(self.path.glob('**/{name}-{version}{suffix}'.format(
                name=name.replace('-', '_'),
                version=str(version),
                suffix=suffix,
            )))
            if paths:
                path = min(paths, key=lambda path: len(path.parts))
                return converter.load(path=path)

        # read from egg-info
        path = self.path / (name + '.egg-info')
        if path.exists():
            return EggInfoConverter().load(path=path)

        # read from dephell config
        path = self.path / 'pyproject.toml'
        if path.exists():
            config = Config().attach_file(path=path, env='main')
            if config is not None:
                section = config.get('to') or config.get('from')
                if section and 'path' in section and 'format' in section:
                    converter = CONVERTERS[section['format']]
                    path = self.path.joinpath(section['path'])
                    return converter.load(path)

        # get from dependencies file
        for fname in FILES:
            path = self.path / fname
            if not path.exists():
                continue
            for converter in CONVERTERS.values():
                if converter.can_parse(path=path):
                    return converter.load(path=path)

        raise LookupError('cannot find dependencies in ' + str(self.path))

    def update_dep_from_root(cls, dep, root) -> None:
        if not dep.description:
            dep.description = root.description
        if not dep.authors:
            dep.authors = root.authors
        if not dep.links:
            dep.links = root.links
        if not dep.classifiers:
            dep.classifiers = root.classifiers
        if not dep.license:
            dep.license = root.license