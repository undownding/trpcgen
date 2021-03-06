from __future__ import print_function

from collections import defaultdict
import os

from . import ast
from .parser import Parser


class SymbolTable(dict):
  def __init__(self, thrift):
    for parent, node in thrift.walk():
      if isinstance(node, ast.Typedef):
        self[node.name.value] = node
      elif isinstance(node, ast.Enum):
        self[node.name.value] = node
      elif isinstance(node, ast.EnumDef):
        self[parent.name.value + '.' + node.name.value] = node.tag
      elif isinstance(node, ast.Const):
        self[node.name.value] = node
      elif isinstance(node, ast.Struct):
        self[node.name.value] = node
      elif isinstance(node, ast.Exception_):
        self[node.name.value] = node
      elif isinstance(node, ast.Service):
        self[node.name.value] = node


class Loader(object):
  class Error(Exception): pass
  class LookupError(Error): pass

  def __init__(self, filename, logger=print):
    self.root = filename
    self.logger = logger
    self.thrifts = {}
    self.modules = {}
    self.includes = {}
    self.parser = Parser()
    self.namespaces = {}
    self.process(self.root)

  def process(self, root, is_include = False):
    real_root = os.path.realpath(root)

    if real_root in self.thrifts:
      return

    self.logger('Processing %s' % real_root)

    with open(real_root) as fp:
      parent = self.thrifts[real_root] = self.parser.parse(fp.read())
    
    if is_include:
      left = real_root.rindex(os.sep)
      include_file = real_root[left+1:].split(".")[0]
      
      namespaces = {}
      for space in parent.namespaces:
        namespaces[space.language_id] = space.name
      self.includes[include_file] = namespaces
    else:
      for space in parent.namespaces:
        self.namespaces[space.language_id] = space.name

    parent_name = os.path.basename(real_root)
    parent_name, _ = os.path.splitext(parent_name)
    if parent_name in self.modules:
      self.logger('Warning: ambiguous include (module %s already exists)' % parent_name)
    if not is_include:
      self.modules[parent_name] = SymbolTable(parent)

    for include in parent.includes:
      real_path = os.path.join(os.path.dirname(real_root), include.path.value)
      self.process(real_path, True)

  def dump(self):
    for filename, thrift in self.thrifts.items():
      self.logger('Dumping %s\n' % filename)
      self.logger('%s\n\n' % thrift)

  def find(self, name, module, recursive=True):
    if module not in self.modules:
      raise self.LookupError('Unknown module %s' % module)

    value = self.modules[module].get(name)

    # Not found, is it prefixed by a module name?
    if value is None:
      if '.' not in name:
        raise self.LookupError('Could not resolve %s from %s' % (name, module))
      prefix, name = name.split('.', 1)
      return self.find(name, prefix)

    if isinstance(value, ast.Identifier) and recursive:
      return self.find(value.value, module, recursive)

    return value

  def lookup(self, name, module=None):
    if module:
      return self.find(name, module)
    for module_name in self.modules:
      try:
        return self.find(name, module_name)
      except self.LookupError:
        continue
