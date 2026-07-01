import os
import re
import shutil
import argparse


def copy_template(src: str, dst: str):
    """Copy template directory `src` to `dst`. `dst` must not exist."""
    if os.path.exists(dst):
        raise FileExistsError(f"Destination '{dst}' already exists.")
    shutil.copytree(src, dst)


def build_replacers(pairs):
    """
    Given a list of (old, new) pairs, build a list of (pattern, repl_func).
    Replacement matches whole words or CamelCase boundaries, case-insensitive.
    """
    replacers = []
    for old, new in pairs:
        # pattern: match old at word boundaries or before/after uppercase letter
        regex = (
                r'(?:(?<=^)|(?<=[^A-Za-z])|(?<=[A-Z]))'
                r'(' + re.escape(old) + r')'
                                        r'(?:(?=$)|(?=[^A-Za-z])|(?=[A-Z]))'
        )
        pattern = re.compile(regex, flags=re.IGNORECASE)

        def make_repl(new):
            def repl(m: re.Match) -> str:
                orig = m.group(1)
                if orig.isupper():
                    return new.upper()
                if orig.islower():
                    return new.lower()
                if orig[0].isupper() and orig[1:].islower():
                    return new.capitalize()
                return new

            return repl

        replacers.append((pattern, make_repl(new)))
    return replacers


def rename_paths(root: str, replacers):
    """
    Rename files and directories bottom-up according to all replacers.
    """
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        # rename files
        for name in filenames:
            new_name = name
            for pattern, repl in replacers:
                new_name = pattern.sub(repl, new_name)
            if new_name != name:
                os.rename(
                    os.path.join(dirpath, name),
                    os.path.join(dirpath, new_name)
                )
        # rename directories
        for name in dirnames:
            new_name = name
            for pattern, repl in replacers:
                new_name = pattern.sub(repl, new_name)
            if new_name != name:
                os.rename(
                    os.path.join(dirpath, name),
                    os.path.join(dirpath, new_name)
                )


def replace_in_files(root: str, replacers, exts):
    """
    Replace text in files under `root` with extensions in `exts`.
    """
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            if any(name.lower().endswith(ext) for ext in exts):
                path = os.path.join(dirpath, name)
                try:
                    text = open(path, 'r', encoding='utf-8').read()
                except UnicodeDecodeError:
                    continue
                new_text = text
                for pattern, repl in replacers:
                    new_text = pattern.sub(repl, new_text)
                if new_text != text:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_text)


def parse_args():
    p = argparse.ArgumentParser(
        description="""
Clone a template directory and perform case-preserving, word-boundary replacements
for multiple placeholder pairs in filenames, directory names, and file contents
(including .py, .bat and .yaml/.yml files).
        """
    )
    p.add_argument('src', help='Template directory to clone')
    p.add_argument('dst', help='Destination directory (must not exist)')
    p.add_argument(
        'replacements', nargs='+',
        help='Replacement pairs in format old:new, e.g. Template:MyProj'
    )
    return p.parse_args()


def main():
    args = parse_args()
    # parse replacement pairs
    pairs = []
    for rep in args.replacements:
        if ':' not in rep:
            raise ValueError(f"Invalid replacement '{rep}', must be old:new")
        old, new = rep.split(':', 1)
        pairs.append((old, new))

    directly_main(args.src, args.dst, pairs)


def directly_main(src, dst, pairs):
    # copy template
    copy_template(src, dst)
    # build replacers
    replacers = build_replacers(pairs)
    # rename files and directories
    rename_paths(dst, replacers)
    # replace in files (.py, .yaml, .yml)
    replace_in_files(dst, replacers, exts=['.py', '.bat', '.yaml', '.yml'])

    print(f"Template from '{src}' cloned to '{dst}'.")
    for old, new in pairs:
        print(f"Replaced '{old}' -> '{new}' (case-preserving, word-boundary) in names and .py/.yaml files.")


if __name__ == '__main__':
    # main()
    from powertrde.env import RES_CORE_DIR, PROJ_DIR

    # _team = input('input team name: ')
    # _scheme = input('input scheme name: ')

    src = r'D:\TranssionProjects\dz_auto_env\pretests\dzppt\decline\decline_gui'
    det = r'D:\TranssionProjects\dz_auto_env\pretests\dzppt\pcss\pcss_gui'
    pairs = [('decline', 'pcss')]
    directly_main(src, det, pairs)
