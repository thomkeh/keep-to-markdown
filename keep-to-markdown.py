import argparse
from datetime import datetime as dt
import glob
import itertools
import json
import mimetypes
from pathlib import Path
from shutil import copy2 as cp
from typing import Literal, TypedDict
from typing_extensions import NotRequired


class Annotation(TypedDict):
    source: Literal["WEBLINK"]
    title: str
    url: str


class Attachment(TypedDict):
    mimetype: Literal["image"]
    filePath: str


class Task(TypedDict):
    text: str
    isChecked: bool


class Label(TypedDict):
    name: str


class Note(TypedDict):
    title: str
    userEditedTimestampUsec: int
    labels: NotRequired[list[Label]]
    textContent: NotRequired[str]
    listContent: NotRequired[list[Task]]
    annotations: NotRequired[list[Annotation]]
    attachments: NotRequired[list[Attachment]]


class Args:
    i: str
    t: bool


def read_write_notes(args: Args):
    source_dir = Path(args.i)
    conv_folders = args.t
    notes = source_dir.glob("*.json")

    for note in notes:
        with open(note, "r", encoding="utf-8") as jsonfile:
            data: Note = json.load(jsonfile)
        tags = []
        if (labels := data.get("labels")) is not None:
            tags = [label["name"] for label in labels]
        else:
            print("No tags available.")

        date: str | None = None
        has_title = False
        match data["title"], data["userEditedTimestampUsec"]:
            case "", 0:  # no title, no timestamp
                filename = dt.now().strftime("%Y%m%dT%H%M%S.%f_edited")
            case title, 0:
                filename = clean_title(title)[:99]
                has_title = True
            case title, timestamp:
                date_obj = dt.fromtimestamp(timestamp / 1000000)
                if title != "":
                    filename = clean_title(title)[:99]
                    has_title = True
                    date = date_obj.isoformat(timespec="seconds")
                else:
                    filename = date_obj.strftime("%Y-%m-%d+%H%M%S")

        # create folders by tags
        if conv_folders and tags:
            subfolder = tags[0]
        else:
            subfolder = ""
        notes_root = Path("notes")
        notes_dir = notes_root / subfolder

        # check if filename exists
        if (md_path := notes_dir / f"{filename}.md").exists():
            print(f"Existing file found: {md_path}")
            # increment duplicate number, if already exists
            for dup_num in itertools.count(1):
                if not md_path.with_name(f"{filename}({dup_num}).md").exists():
                    break
                print(
                    f'File "{notes_dir}{filename}({dup_num}).md" exists, increment'
                    " number..."
                )

            filename = f"{filename}({dup_num})"  # type: ignore
            print(f"New filename: {filename}.md")

        # create path to notes
        if not notes_dir.exists():
            notes_dir.mkdir()
            (notes_dir / "resources").mkdir()
            print(f"Create tag and resources subfolder: {subfolder}")

        # create Markdown file
        print(f'Convert "{filename}" to markdown file.')
        md_path = notes_dir / f"{filename}.md"
        with md_path.open("w", encoding="utf-8") as mdfile:
            if has_title:
                mdfile.write(f"---\n")
                if date is not None:
                    mdfile.write(f"date: {date}\n")
                # add tags
                if tags:
                    mdfile.write(f"{format_tags(tags)}\n")
                mdfile.write(f"---\n\n")
            elif tags:
                mdfile.write(f"[[{']] [['.join(tags)}]]\n")
            # add text content
            if (text_content := data.get("textContent")) is not None:
                mdfile.write(f"{text_content}\n\n")
            else:
                print("No text content available.")
            # add tasklist
            if (tasklist := data.get("listContent")) is not None:
                mdfile.write(f"{read_tasklist(tasklist)}\n\n")
            else:
                print("No tasklist available.")
            # add annotations
            if (annotations := data.get("annotations")) is not None:
                mdfile.write(f"{read_annotations(annotations)}")
            else:
                print("No annotations available.")
            # add attachments
            if (attachments := data.get("attachments")) is not None:
                mdfile.write(f"{read_attachments(attachments, source_dir, notes_dir)}")
            else:
                print("No attachments available.")


def clean_title(title: str) -> str:
    title = title.replace("\\", "_").replace("/", "_").replace("|", "_")
    title = title.replace("<", "-").replace(">", "-").replace(":", " ")
    title = title.replace("?", "").replace('"', "").replace("*", "")
    title = title.replace("\n", "")
    return title


def format_tags(tags: list[str]) -> str:
    return f"tags: [{', '.join(tags)}]"


def read_tasklist(list: list[Task]) -> str:
    content_list = "*Tasklist:*\n"
    for entry in list:
        text = entry["text"]
        if entry["isChecked"] is True:
            content_list += f"- [x] {text}\n"
        else:
            content_list += f"- [ ] {text}\n"
    return content_list


def read_annotations(list: list[Annotation]) -> str:
    annotations_list = "*Weblinks:*"
    for entry in list:
        if entry["source"] == "WEBLINK":
            title = entry["title"]
            url = entry["url"]
            annotations_list += f" [{title}]({url});"
    return annotations_list


def read_attachments(list: list[Attachment], path: Path, notespath: Path) -> str:
    attachments_list = "*Attachments:*\n"
    for entry in list:
        if "image" in entry["mimetype"]:
            image = entry["filePath"]
            if copy_file(image, path, notespath) is False:
                # If the file could not be found,
                # it will be checked if the file can be found
                # another file format.
                # Google used '.jpeg' instead of '.jpg'
                image_type = mimetypes.guess_type(str(path / image))
                assert image_type[0] is not None
                types = mimetypes.guess_all_extensions(image_type[0])
                for type in types:
                    if type in image:
                        image_name = image.replace(type, "")
                        for t in types:
                            if len(glob.glob(f"{path}{image_name}{t}")) > 0:
                                image = f"{image_name}{t}"
                                print(f'Found "{image}"')
                                copy_file(image, path, notespath)
            attachments_list += f"![{image}](resources/{image})\n"
    return attachments_list


def copy_file(file: str, source_dir: Path, notes_dir: Path) -> bool:
    try:
        cp(source_dir / file, notes_dir / "resources")
    except FileNotFoundError:
        print(f'File "{file}" not found in {source_dir}')
        return False
    else:
        return True


def create_folder():
    try:
        workpath = Path("notes") / "resources"
        if not workpath.exists():
            workpath.mkdir(parents=True)
            print('Create folder "notes" - home of markdown files.')
    except OSError:
        print("Creation of folders failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Converting Google Keep notes to markdown files."
    )
    parser.add_argument(
        "-i", metavar="PATH", required=True, help="The path to the Takeout folder."
    )
    parser.add_argument(
        "-t", action="store_true", help="Use folders instead of front-matter for tags."
    )
    args = Args()
    parser.parse_args(namespace=args)

    create_folder()
    try:
        read_write_notes(args)
    except IndexError:
        print("Please enter a correct path!")
