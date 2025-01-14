import time
from typing import Optional, Sequence

import click

from beet import Project
from beet.toolchain.cli import beet, echo, error_handler, message_fence

pass_project = click.make_pass_decorator(Project)  # type: ignore


@beet.command()
@pass_project
@click.option(
    "-l",
    "--link",
    metavar="WORLD",
    help="Link the project before building.",
)
@click.option(
    "-n",
    "--no-link",
    is_flag=True,
    help="Don't copy the output to the linked Minecraft world.",
)
def build(project: Project, link: Optional[str], no_link: bool):
    """Build the current project."""
    text = "Linking and building project..." if link else "Building project..."
    with message_fence(text):
        if link:
            echo("\n".join(project.link(world=link)))
        project.build(no_link)


@beet.command()
@pass_project
@click.option(
    "-r",
    "--reload",
    is_flag=True,
    help="Enable live data pack reloading.",
)
@click.option(
    "-l",
    "--link",
    metavar="WORLD",
    help="Link the project before watching.",
)
@click.option(
    "-n",
    "--no-link",
    is_flag=True,
    help="Don't copy the output to the linked Minecraft world.",
)
@click.option(
    "-i",
    "--interval",
    metavar="SECONDS",
    default=0.6,
    help="Configure the polling interval.",
)
def watch(
    project: Project,
    reload: bool,
    link: Optional[str],
    no_link: bool,
    interval: float,
):
    """Watch the project directory and build on file changes."""
    text = "Linking and watching project..." if link else "Watching project..."
    with message_fence(text):
        if link:
            echo("\n".join(project.link(world=link)))

        for changes in project.watch(interval):
            filename, action = next(iter(changes.items()))

            text = (
                f"{action.capitalize()} '{filename}'"
                if changes == {filename: action}
                else f"{len(changes)} changes detected"
            )

            now = time.strftime("%H:%M:%S")
            change_time = click.style(now, fg="green", bold=True)
            echo(f"{change_time} {text}")

            if reload:
                project.config.pipeline.append("beet.contrib.livereload")

            with error_handler(format_padding=1):
                project.build(no_link)


@beet.command()
@pass_project
@click.argument("patterns", nargs=-1)
@click.option(
    "-c",
    "--clear",
    is_flag=True,
    help="Clear the cache.",
)
def cache(project: Project, patterns: Sequence[str], clear: bool):
    """Inspect or clear the cache."""
    if clear:
        with message_fence("Clearing cache..."):
            if cache_names := ", ".join(project.clear_cache(patterns)):
                echo(f"Cache cleared successfully: {cache_names}.\n")
            else:
                echo(
                    "No matching results.\n"
                    if patterns
                    else "The cache is already cleared.\n"
                )
    else:
        with message_fence("Inspecting cache..."):
            echo(
                "\n".join(project.inspect_cache(patterns))
                or (
                    "No matching results.\n"
                    if patterns
                    else "The cache is completely clear.\n"
                )
            )


@beet.command()
@pass_project
@click.argument("world", required=False)
@click.option(
    "--minecraft",
    metavar="DIRECTORY",
    help="Path to the .minecraft directory.",
)
@click.option(
    "--data-pack",
    metavar="DIRECTORY",
    help="Path to the data packs directory.",
)
@click.option(
    "--resource-pack",
    metavar="DIRECTORY",
    help="Path to the resource packs directory.",
)
@click.option(
    "-c",
    "--clear",
    is_flag=True,
    help="Clear the link.",
)
def link(
    project: Project,
    world: Optional[str],
    minecraft: Optional[str],
    data_pack: Optional[str],
    resource_pack: Optional[str],
    clear: bool,
):
    """Link the generated resource pack and data pack to Minecraft."""
    if clear:
        with message_fence("Clearing project link..."):
            project.clear_link()
    else:
        with message_fence("Linking project..."):
            echo("\n".join(project.link(world, minecraft, data_pack, resource_pack)))
