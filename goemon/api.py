import copy
import hashlib
import logging
import os
import shutil
import tempfile
import yaml

import requests


logger = logging.getLogger(__name__)

PROPERTIES = [
    'meta',
    'description',
    'script',
    'param',
    'paramschema',
]

META_BOOLEAN_PROPERTIES = ['public', 'importable', 'distributable']
META_STRING_OR_NONE_PROPERTIES = ['creatorLogType', 'authorLogType']
META_STRING_OR_EMPTY_PROPERTIES = ['title']

class Task(object):
    def __init__(self, obj=None):
        self.obj = obj if obj is not None else {}
        self.changed = {}
        self.dir_files = None
        self._download_files()

    def destroy(self):
        if not self.dir_files:
            return
        logger.info(f'Cleanup... {self.dir_files}')
        shutil.rmtree(self.dir_files)
        self.dir_files = None

    @property
    def meta(self):
        obj = {}
        for key in META_BOOLEAN_PROPERTIES:
            obj[key] = self.obj.get(key, False)
        for key in META_STRING_OR_NONE_PROPERTIES:
            obj[key] = self.obj.get(key, 'none')
        for key in META_STRING_OR_EMPTY_PROPERTIES:
            obj[key] = self.obj.get(key, '')
        return yaml.dump(obj, allow_unicode=True)

    @meta.setter
    def meta(self, value):
        obj = yaml.load(value, yaml.SafeLoader)
        for key in META_BOOLEAN_PROPERTIES:
            self.obj[key] = obj.get(key, False)
            self.changed[key] = True
        for key in META_STRING_OR_NONE_PROPERTIES:
            self.obj[key] = obj.get(key, 'none')
            self.changed[key] = True
        for key in META_STRING_OR_EMPTY_PROPERTIES:
            self.obj[key] = obj.get(key, '')
            self.changed[key] = True

    @property
    def description(self):
        return self.obj.get('description', '')

    @description.setter
    def description(self, value):
        self.obj['description'] = value
        self.changed['description'] = True

    @property
    def script(self):
        return self.obj.get('script', '')

    @script.setter
    def script(self, value):
        self.obj['script'] = value
        self.changed['script'] = True

    @property
    def param(self):
        return yaml.dump(self.obj['param'], allow_unicode=True) if self.obj.get('param', None) is not None else ''

    @param.setter
    def param(self, value):
        param = yaml.load(value, yaml.SafeLoader)
        self._validate_param(param)
        self.obj['param'] = param
        self.changed['param'] = True

    @property
    def paramschema(self):
        return yaml.dump(self.obj['paramschema'], allow_unicode=True) if self.obj.get('paramschema', None) is not None else ''

    @paramschema.setter
    def paramschema(self, value):
        paramschema = yaml.load(value, yaml.SafeLoader)
        self._validate_paramschema(paramschema)
        self.obj['paramschema'] = paramschema
        self.changed['paramschema'] = True

    @property
    def files(self):
        files_yaml = yaml.dump([self._get_file_attr(file) for file in self.obj['files']], allow_unicode=True) \
            if self.obj.get('files', None) is not None else ''
        files_path = [(self.dir_files, file['data']['attributes']['name'])
                      for file in self.obj.get('files', [])]
        return files_yaml, files_path

    @files.setter
    def files(self, value):
        oldfiles = self.obj.get('files', [])
        files_yaml, files_path = value
        newfiles = []
        newdata_files = []
        for file in yaml.load(files_yaml, yaml.SafeLoader):
            self._validate_file(file)
            filepath = [os.path.join(d, f) for d, f in files_path if f == file['name']][0]
            with open(filepath, 'rb') as f:
                hash = hashlib.sha256(f.read()).hexdigest()
            oldfiles_matched = [f
                                for f in oldfiles
                                if f['data']['attributes']['name'] == file['name'] and
                                    f['data']['attributes']['hashSHA256'] == hash]
            if len(oldfiles_matched) > 0:
                logger.info(f'File properties updated: {filepath}')
                newfile = copy.deepcopy(oldfiles_matched[0])
                newfile['data']['attributes'].update(file)
                newfiles.append(newfile)
                continue
            logger.info(f'New file: {filepath} - hash: {hash}')
            attr = {
                'hashSHA256': hash,
                'size': os.path.getsize(filepath),
                'lastModified': int(os.path.getmtime(filepath) * 1000),
            }
            attr.update(file)
            newfiles.append({
                'type': 'files',
                'data': {
                    'attributes': attr,
                },
            })
            newdata_files.append((file['name'], hash, filepath))
        self.obj['files'] = newfiles
        self.obj['files_data'] = newdata_files
        self.changed['files'] = True

    def serialize_as_task(self):
        data = {}
        all_properties = PROPERTIES + ['files'] + META_BOOLEAN_PROPERTIES \
            + META_STRING_OR_EMPTY_PROPERTIES + META_STRING_OR_NONE_PROPERTIES
        for prop in all_properties:
            if prop == 'meta':
                continue
            if not self.changed.get(prop, False):
                continue
            data[prop] = self.obj[prop]
        return data

    def get_data_files(self):
        if 'files_data' not in self.obj:
            return []
        return self.obj['files_data']

    def _download_files(self):
        files = self.obj.get('files', None)
        if files is None or len(files) == 0:
            return
        self.dir_files = tempfile.mkdtemp()
        for file in files:
            path = os.path.join(self.dir_files, file['data']['attributes']['name'])
            path_dir, _ = os.path.split(path)
            os.makedirs(path_dir, exist_ok=True)
            with open(path, 'wb') as f:
                url = file['links']['download']
                r = requests.get(url, stream=True)
                r.raise_for_status()
                shutil.copyfileobj(r.raw, f)

    def _validate_file(self, file):
        if 'name' not in file:
            raise ValueError(f'name is not defined: {file}')
        value = file['name']
        if not isinstance(value, str):
            raise ValueError(f'name is not str: {value}')
        if 'type' not in file:
            raise ValueError(f'type is not defined: {file}')
        value = file['type']
        if not isinstance(value, str):
            raise ValueError(f'type is not str: {value}')
        if 'importType' not in file:
            raise ValueError(f'importType is not defined: {file}')
        value = file['importType']
        if not isinstance(value, str):
            raise ValueError(f'importType is not str: {value}')
        if 'preload' not in file:
            raise ValueError(f'preload is not defined: {file}')
        value = file['preload']
        if not isinstance(value, bool):
            raise ValueError(f'preload is not str: {value}')
        if 'priority' not in file:
            raise ValueError(f'priority is not defined: {file}')
        value = file['priority']
        if not isinstance(value, int):
            raise ValueError(f'priority is not int: {value}')

    def _validate_param(self, param):
        if param is None:
            return
        if not isinstance(param, list):
            raise ValueError(f'param is not list or none: {param}')
        for p in param:
            self._validate_param_field(p)

    def _validate_param_field(self, elem):
        if 'name' not in elem:
            raise ValueError(f'name is not defined: {elem}')
        elemname = elem['name']
        if not isinstance(elemname, str):
            raise ValueError(f'name is not str: {elemname}')
        if 'value' not in elem:
            raise ValueError(f'value is not defined: {elem}')
        elemvalue = elem['value']
        if not isinstance(elemvalue, str):
            raise ValueError(f'value is not str: {elemvalue}')

    def _validate_paramschema(self, paramschema):
        if paramschema is None:
            return
        if not isinstance(paramschema, list):
            raise ValueError(f'paramschema is not list or none: {paramschema}')
        for p in paramschema:
            self._validate_paramschema_field(p)

    def _validate_paramschema_field(self, elem):
        types = ['string', 'integer', 'number', 'file', 'boolean', 'url']
        if 'name' not in elem:
            raise ValueError(f'name is not defined: {elem}')
        elemname = elem['name']
        if not isinstance(elemname, str):
            raise ValueError(f'name is not str: {elemname}')
        if 'type' not in elem:
            raise ValueError(f'type is not defined: {elem}')
        elemtype = elem['type']
        if elemtype not in types:
            raise ValueError(f'unexpected type: {elemtype}')

    def _get_file_attr(self, file):
        attr = file['data']['attributes']
        r = {}
        for key in ['importType', 'name', 'preload', 'priority', 'type']:
            r[key] = attr[key]
        return r

class V1API(object):
    def __init__(self, token):
        self.token = token
        if token is None:
            raise ValueError('token is not set')

    def get_task(self, task_id, shared=False):
        return self._get('tasks' if not shared else 'shares', task_id)

    def patch_task(self, task_id, task, shared=False):
        data = {
            'type': 'tasks',
            'data': {
                'attributes': task.serialize_as_task(),
            },
        }
        data_files = task.get_data_files()
        return self._patch('tasks' if not shared else 'shares', task_id, data, data_files)

    def _get(self, task_type, task_id):
        logger.info(f'Acquiring for task({task_type}/{task_id})')
        resp = requests.get(
            self._get_url(task_type, task_id),
            headers={'Authorization': f'Bearer {self.token}'},
        )
        resp.raise_for_status()
        respjson = resp.json()
        logger.info(f'Task acquired({task_type}/{task_id}): {respjson}')
        return Task(respjson['data']['attributes'])

    def _patch(self, task_type, task_id, data, data_files):
        logger.info(f'Patch for task({task_type}/{task_id}): {data}')
        resp = requests.patch(
            self._get_url(task_type, task_id),
            json=data,
            headers={'Authorization': f'Bearer {self.token}'},
        )
        respjson = resp.json()
        logger.info(f'Patched for task({task_type}/{task_id}): {respjson}')
        resp.raise_for_status()
        for filename, hash, filepath in data_files:
            logger.info(f'Uploading {filepath}...')
            files = [file
                     for file in respjson['data']['attributes']['files']
                     if file['data']['attributes']['hashSHA256'] == hash and
                         file['data']['attributes']['name'] == filename]
            if len(files) == 0:
                raise IOError(f'Unexpected result: no entities for {filename}')
            with open(filepath, 'rb') as f:
                r = requests.put(
                    files[0]['links']['upload'],
                    files={'content': f},
                )
                r.raise_for_status()
        return Task(respjson['data']['attributes'])

    def _get_url(self, task_type, task_id):
        return f'https://goemon.cloud/api/v1/{task_type}/{task_id}'