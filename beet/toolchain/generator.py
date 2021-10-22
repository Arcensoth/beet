__all__ = [
    "Generator",
    "Draft",
]


import json
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    DefaultDict,
    Iterable,
    Iterator,
    Optional,
    Tuple,
    TypeVar,
    overload,
)

from beet.core.file import TextFileBase
from beet.core.utils import TextComponent
from beet.library.base import NamespaceFile
from beet.library.data_pack import DataPack, Function
from beet.library.resource_pack import ResourcePack

from .tree import TreeNode, generate_tree
from .utils import LazyFormat, stable_hash

if TYPE_CHECKING:
    from .context import Context


T = TypeVar("T", contravariant=True)
GeneratorType = TypeVar("GeneratorType", bound="Generator")


@dataclass
class Generator:
    """Helper for generating assets and data pack resources."""

    ctx: "Context"
    scope: Tuple[Any, ...] = ()
    registry: DefaultDict[Tuple[Any, ...], int] = field(
        default_factory=lambda: defaultdict(int)  # type: ignore
    )

    assets: ResourcePack = field(default_factory=ResourcePack)
    data: DataPack = field(default_factory=DataPack)
    parent_assets: ResourcePack = field(default_factory=ResourcePack)
    parent_data: DataPack = field(default_factory=DataPack)

    def __getitem__(self: GeneratorType, key: Any) -> GeneratorType:
        return self.__class__(
            ctx=self.ctx,
            scope=self.scope + (key,),
            registry=self.registry,
            assets=self.assets,
            data=self.data,
            parent_assets=self.parent_assets,
            parent_data=self.parent_data,
        )

    @contextmanager
    def push(self) -> Iterator[None]:
        """Temporarily push the current state into the root context generator."""
        root = self.ctx.generate

        previous_scope = root.scope
        previous_assets = root.assets
        previous_data = root.data
        previous_parent_assets = root.parent_assets
        previous_parent_data = root.parent_data

        root.scope = self.scope
        root.assets = self.assets
        root.data = self.data
        root.parent_assets = self.parent_assets
        root.parent_data = self.parent_data

        try:
            yield
        finally:
            root.scope = previous_scope
            root.assets = previous_assets
            root.data = previous_data
            root.parent_assets = previous_parent_assets
            root.parent_data = previous_parent_data

    def get_prefix(self, separator: str = ".") -> str:
        """Join the serializable parts of the scope into a key prefix."""
        prefix = ()
        if prefix_value := self.ctx.meta.get("generate_prefix"):
            prefix = (prefix_value,)

        return "".join(
            part + separator
            for part in prefix + self.scope
            if part and isinstance(part, str)
        )

    def get_increment(self, *key: Any) -> int:
        """Return the current value for the given key and increment it."""
        key = (self.ctx.project_id, *self.scope, *key)
        count = self.registry[key]
        self.registry[key] += 1
        return count

    def format(self, fmt: str, hash: Any = None) -> str:
        """Generate a unique key depending on the given template."""
        env = {
            "namespace": self.ctx.meta.get("generate_namespace", self.ctx.project_id),
            "path": LazyFormat(lambda: self.get_prefix("/")),
            "scope": LazyFormat(lambda: self.get_prefix()),
            "incr": LazyFormat(lambda: self.get_increment(fmt)),
        }

        if hash is not None:
            value = hash
            env["hash"] = LazyFormat(lambda: stable_hash(value))
            env["short_hash"] = LazyFormat(lambda: stable_hash(value, short=True))

        return fmt.format_map(env)

    @overload
    def __call__(
        self,
        fmt: str,
        file_instance: NamespaceFile,
        *,
        hash: Any = None,
    ) -> str:
        ...

    @overload
    def __call__(
        self,
        fmt: str,
        *,
        render: TextFileBase[Any],
        hash: Any = None,
        **kwargs: Any,
    ) -> str:
        ...

    @overload
    def __call__(
        self,
        file_instance: NamespaceFile,
        *,
        hash: Any = None,
    ) -> str:
        ...

    @overload
    def __call__(
        self,
        *,
        render: TextFileBase[Any],
        hash: Any = None,
        **kwargs: Any,
    ) -> str:
        ...

    def __call__(
        self,
        *args: Any,
        render: Optional[TextFileBase[Any]] = None,
        hash: Any = None,
        **kwargs: Any,
    ) -> Any:
        file_instance: NamespaceFile

        if render:
            file_instance = render  # type: ignore
            fmt = args[0] if args else None
        elif len(args) == 2:
            fmt, file_instance = args
        else:
            file_instance = args[0]
            fmt = None

        if hash is None and not render:
            hash = lambda: file_instance.ensure_serialized()

        file_type = type(file_instance)
        key = (
            self[file_type].path(fmt, hash) if fmt else self[file_type].path(hash=hash)
        )

        pack = (
            self.data
            if file_type in self.data.namespace_type.field_map
            else self.assets
        )

        pack[key] = file_instance

        if render:
            with self.ctx.override(
                render_path=key,
                render_group=pack.namespace_type.field_map[file_type],
            ):
                self.ctx.template.render_file(render, **kwargs)

        return key

    def path(self, fmt: str = "generated_{incr}", hash: Any = None) -> str:
        """Generate a scoped resource path."""
        template = self.ctx.meta.get("generate_path", "{namespace}:{path}")
        return self.format(template + fmt, hash)

    def id(self, fmt: str = "{incr}", hash: Any = None) -> str:
        """Generate a scoped id."""
        template = self.ctx.meta.get("generate_id", "{namespace}.{scope}")
        return self.format(template + fmt, hash)

    def hash(
        self,
        fmt: str,
        hash: Any = None,
        short: bool = False,
    ) -> str:
        """Generate a scoped hash."""
        template = self.ctx.meta.get("generate_hash", "{namespace}.{scope}")
        return stable_hash(self.format(template + fmt, hash), short)

    def objective(
        self,
        fmt: str = "{incr}",
        hash: Any = None,
        criterion: str = "dummy",
        display: Optional[TextComponent] = None,
    ) -> str:
        """Generate a scoreboard objective."""
        template = self.ctx.meta.get("generate_objective", "{namespace}.{scope}")
        key = self.format(template + fmt, hash)
        objective = stable_hash(key)
        display = json.dumps(display or key)

        scoreboard = self.ctx.meta.setdefault("generate_scoreboard", {})
        scoreboard[objective] = f"{criterion} {display}"

        return objective

    @overload
    def function_tree(
        self,
        fmt: str,
        items: Iterable[T],
        *,
        key: Optional[Callable[[T], int]] = None,
        hash: Any = None,
    ) -> Iterator[Tuple[TreeNode[T], Function]]:
        ...

    @overload
    def function_tree(
        self,
        items: Iterable[T],
        *,
        key: Optional[Callable[[T], int]] = None,
        hash: Any = None,
    ) -> Iterator[Tuple[TreeNode[T], Function]]:
        ...

    def function_tree(
        self,
        *args: Any,
        key: Any = None,
        hash: Any = None,
    ) -> Iterator[Tuple[TreeNode[Any], Function]]:
        """Generate a function tree."""
        if len(args) == 2:
            fmt, items = args
        else:
            items = args[0]
            fmt = None

        if hash is None:
            hash = lambda: str(items)

        root = self[Function].path(fmt, hash) if fmt else self[Function].path(hash=hash)

        for node in generate_tree(root, items, key):
            yield node, self.data.functions.setdefault(node.parent, Function())

    def draft(self) -> "Draft":
        """Return a new draft."""
        return Draft(
            ctx=self.ctx,
            scope=self.scope,
            registry=self.registry,
            assets=ResourcePack(),
            data=DataPack(),
            parent_assets=self.assets,
            parent_data=self.data,
        )


class Draft(Generator):
    """Generator that works on an intermediate resource pack and data pack."""

    def apply(self):
        """Merge the working resource pack and data pack into the context."""
        if self.assets is not self.parent_assets:
            self.parent_assets.merge(self.assets)
        if self.data is not self.parent_data:
            self.parent_data.merge(self.data)

    def cache(
        self,
        name: str,
        key: str,
        zipped: bool = False,
        apply: bool = False,
    ) -> Iterator["Draft"]:
        """Try to load the draft from the cache or yield once to let the body of the loop generate it."""
        cache = self.ctx.cache[name]

        suffix = ".zip" if zipped else ""
        cached_resource_pack = cache.directory / f"draft_resource_pack{suffix}"
        cached_data_pack = cache.directory / f"draft_data_pack{suffix}"

        key = f"{key} {zipped=}"

        if cache.json.get("draft_key") == key:
            self.assets.load(cached_resource_pack)
            self.data.load(cached_data_pack)
            if apply:
                self.apply()
            return

        yield self

        if self.assets:
            self.assets.save(path=cached_resource_pack, overwrite=True)
        if self.data:
            self.data.save(path=cached_data_pack, overwrite=True)

        cache.json["draft_key"] = key
        if apply:
            self.apply()
