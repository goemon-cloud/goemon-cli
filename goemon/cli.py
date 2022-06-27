import argparse
import difflib
import io
import logging
import os
import shutil
import sys
import yaml

from .api import V1API, PROPERTIES


logger = logging.getLogger(__name__)

DEFAULT_FILENAMES = {
    'meta': 'meta.yml',
    'description': 'description.md',
    'script': 'script.js',
    'param': 'param.yml',
    'paramschema': 'paramschema.yml',
    'files': 'files/',
}

parser = argparse.ArgumentParser()
parser.add_argument(
    '--description',
    default=None,
    help='Path to/from which to save/load the description. - means stdin/stdout',
)
parser.add_argument(
    '--script',
    default=None,
    help='Path to/from which to save/load the script. - means stdin/stdout',
)
parser.add_argument(
    '--param',
    default=None,
    help='Path to/from which to save/load the parameters. - means stdin/stdout',
)
parser.add_argument(
    '--paramschema',
    default=None,
    help='Path to/from which to save/load the parameter schema. - means stdin/stdout',
)
parser.add_argument(
    '--meta',
    default=None,
    help='Path to/from which to save/load the metadata. - means stdin/stdout',
)
parser.add_argument(
    '--files',
    default=None,
    help='Path to/from which to save/load the files. - means stdin/stdout',
)
parser.add_argument(
    '--all',
    action='store_const',
    const=True,
    default=False,
    help='Import/export all types of data. If no filename is specified, use default',
)
parser.add_argument(
    '--base-dir',
    '-d',
    default='.',
    help='Base directory',
)
parser.add_argument(
    '--overwrite',
    action='store_const',
    const=True,
    default=False,
    help='Specify if overwrite files',
)
parser.add_argument(
    '--dry-run',
    action='store_const',
    const=True,
    default=False,
    help='Specify if check mode',
)
parser.add_argument(
    '--shared',
    action='store_const',
    const=True,
    default=False,
    help='Specify if the task is Shared Task',
)
parser.add_argument(
    '--verbose',
    '-v',
    action='store_const',
    const=True,
    default=False,
    help='Verbose output',
)
parser.add_argument(
    'subcommand',
    metavar='subcommand',
    nargs=1,
    help='import|export',
)
parser.add_argument(
    'target_id',
    metavar='target_id',
    nargs=1,
    help='Task ID/Shared ID',
)

def get_stream(args, dest, mode, stdstream):
    if dest == '-':
        return stdstream
    path = os.path.join(args.base_dir, dest)
    if mode == 'w' and os.path.exists(path) and not args.overwrite:
        raise ValueError(f'File already exists: {path}')
    if mode in ['wb', 'rb']:
        return open(path, mode)
    return open(path, mode, encoding='utf8')

def process_import(args, task, prop):
    value = getattr(task, prop)
    dest = getattr(args, prop)
    if args.all and dest is None:
        dest = DEFAULT_FILENAMES[prop]
    if dest is None:
        return
    with get_stream(args, dest, 'w', sys.stdout) as stream:
        stream.write(value)

def process_files_import(args, task):
    value, files = task.files
    dest_dir = args.files
    if dest_dir is not None:
        dest_dir = os.path.join(args.base_dir, dest_dir)
    elif args.all and dest_dir is None:
        dest_dir = os.path.join(args.base_dir, DEFAULT_FILENAMES['files'])
    if dest_dir is None:
        return
    os.makedirs(dest_dir, exist_ok=True)
    files_yaml = os.path.join(dest_dir, '.files.yml')
    if os.path.exists(files_yaml) and not args.overwrite:
        raise ValueError(f'File already exists: {files_yaml}')
    with open(files_yaml, 'w', encoding='utf8') as stream:
        stream.write(value)
    for src_dir, filepath in files:
        logger.info(f'Copy {filepath}, {src_dir} -> {dest_dir}')
        dest_path = os.path.join(dest_dir, filepath)
        if os.path.exists(dest_path) and not args.overwrite:
            raise ValueError(f'File already exists: {dest_path}')
        dest_path_dir, _ = os.path.split(dest_path)
        os.makedirs(dest_path_dir, exist_ok=True)
        shutil.copyfile(os.path.join(src_dir, filepath), dest_path)

def process_export(args, task, prop):
    src = getattr(args, prop)
    filename = DEFAULT_FILENAMES[prop]
    if args.all and src is None:
        src = filename
    if src is None:
        return
    with get_stream(args, src, 'r', sys.stdout) as stream:
        value = stream.read()
    if args.dry_run:
        oldvalue = getattr(task, prop)
        sys.stdout.writelines(difflib.unified_diff(
            io.StringIO(oldvalue).readlines(),
            io.StringIO(value).readlines(),
            f'a/{filename}',
            f'b/{filename}',
        ))
    setattr(task, prop, value)

def process_files_export(args, task):
    src_dir = args.files
    src_path = src_dir
    if src_dir is not None:
        src_dir = os.path.join(args.base_dir, src_dir)
    elif args.all and src_dir is None:
        src_dir = os.path.join(args.base_dir, DEFAULT_FILENAMES['files'])
        src_path = DEFAULT_FILENAMES['files']
    if src_dir is None:
        return
    files_yaml_path = os.path.join(src_dir, '.files.yml')
    with open(files_yaml_path, 'r', encoding='utf8') as stream:
        files_yaml = stream.read()
    files_path = []
    for file in yaml.load(files_yaml, yaml.SafeLoader):
        filename = file['name']
        if not os.path.exists(os.path.join(src_dir, filename)):
            raise ValueError(f'File not found: {src_dir}')
        files_path.append((src_dir, filename))
    if args.dry_run:
        oldvalue, oldfiles_path = task.files
        sys.stdout.writelines(difflib.unified_diff(
            io.StringIO(oldvalue).readlines(),
            io.StringIO(files_yaml).readlines(),
            f'a/.files.yml',
            f'b/.files.yml',
        ))
        newfilenames = set([filename for _, filename in files_path])
        oldfilenames = set([filename for _, filename in oldfiles_path])
        filenames = sorted(list(newfilenames | oldfilenames))
        for filename in filenames:
            if filename in newfilenames and filename not in oldfilenames:
                sys.stdout.writelines([f'New file - b/{src_path}/{filename}\n'])
                continue
            if filename not in newfilenames and filename in oldfilenames:
                sys.stdout.writelines([f'Deleted file - a/{src_path}/{filename}\n'])
                continue
            file = os.path.join(src_dir, filename)
            oldfile = os.path.join(
                [oldfile_dir for oldfile_dir, oldfilename in oldfiles_path if oldfilename == filename][0],
                filename,
            )
            with open(oldfile, 'rb') as oldf:
                with open(file, 'rb') as f:
                    lines = difflib.diff_bytes(
                        difflib.unified_diff,
                        oldf.readlines(),
                        f.readlines(),
                        f'a/{src_path}/{filename}'.encode('utf8'),
                        f'b/{src_path}/{filename}'.encode('utf8'),
                    )
                    try:
                        sys.stdout.writelines([l.decode('utf8') for l in lines])
                    except UnicodeDecodeError:
                        sys.stdout.writelines(
                            [f'Binary files changed - a/{src_path}/{filename}, b/{src_path}/{filename}\n']
                        )
    task.files = (files_yaml, files_path)

def flush_export(args, api, task):
    if args.dry_run:
        logger.info('Finished: check-mode')
        return
    api.patch_task(args.target_id[-1], task, shared=args.shared)

def main():
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARN,
    )
    token = os.environ.get('GOEMON_TOKEN', None)
    if token is None:
        raise ValueError('Environment variable GOEMON_TOKEN missing')
    api = V1API(token=token)
    task = api.get_task(args.target_id[-1], shared=args.shared)
    if all([getattr(args, prop) is None for prop in PROPERTIES]) and args.files is None and not args.all:
        raise ValueError('No files specified')
    if len([prop for prop in PROPERTIES if getattr(args, prop) == '-']) > 1:
        raise ValueError('"-" cannot be set more than once')
    for prop in PROPERTIES:
        if args.subcommand[0] == 'import':
            process_import(args, task, prop)
        elif args.subcommand[0] == 'export':
            process_export(args, task, prop)
        else:
            raise ValueError(f'Unexpected subcommand: {args.subcommand[0]}')
    if args.subcommand[0] == 'import':
        process_files_import(args, task)
    elif args.subcommand[0] == 'export':
        process_files_export(args, task)
        flush_export(args, api, task)
    task.destroy()
