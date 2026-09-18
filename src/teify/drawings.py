"""Render simple ODF rectangles and Bezier paths without guessing geometry.

ODF 1.3 part 3, sections 19.145 (enhanced path) and 19.171 (formula).
Unsupported operators, transforms, paint effects and path commands fail closed.
"""
import ast
import math
import operator
import re

from lxml import etree
from .document import NS, qn

SVG = 'http://www.w3.org/2000/svg'
ODF_SVG = 'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0'


def millimetres(value):
    match = re.fullmatch(r'([-+]?(?:\d+\.?\d*|\.\d+))(mm|cm|in|pt|pc|px)?', value)
    if not match or (not match[2] and float(match[1]) != 0):
        raise ValueError(f'Unsupported drawing length: {value}')
    return float(match[1]) * {'mm':1, 'cm':10, 'in':25.4, 'pt':25.4/72, 'pc':25.4/6, 'px':25.4/96, None:1}[match[2]]


class EnhancedPath:
    def __init__(self, geometry):
        self.equations = {n.get(qn('draw','name')): n.get(qn('draw','formula'))
                          for n in geometry.findall('draw:equation', NS)}
        self.values = {f'm{i}': float(v) for i,v in enumerate(geometry.get(qn('draw','modifiers'), '').split())}
        self.active = set()

    def value(self, name):
        if name in self.values:
            return self.values[name]
        if name in self.active or name not in self.equations:
            raise ValueError(f'Unsupported or cyclic drawing equation: {name}')
        self.active.add(name)
        formula = re.sub(r'\$(\d+)', r'm\1', self.equations[name]).replace('?', '')
        value = self.evaluate(ast.parse(formula.strip(), mode='eval').body)
        self.active.remove(name)
        if not math.isfinite(value):
            raise ValueError('Non-finite drawing coordinate')
        self.values[name] = value
        return value

    def evaluate(self, node):
        operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.Name):
            return self.value(node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in operations:
            return operations[type(node.op)](self.evaluate(node.left), self.evaluate(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return (-1 if isinstance(node.op, ast.USub) else 1) * self.evaluate(node.operand)
        raise ValueError('Unsupported drawing formula; manual rendering required')

    def convert(self, source):
        source = re.sub(r'\?([A-Za-z][A-Za-z0-9_]*)|\$(\d+)',
                        lambda m: format(self.value(m[1] or 'm'+m[2]), '.12g'), source)
        # A final N paints the current subpaths; it does not close them.
        source = re.sub(r'\s*N\s*$', '', source)
        tokens = re.findall(r'[MLCQZ]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', source)
        if re.sub(r'[\s,]', '', source) != ''.join(tokens):
            raise ValueError('Unsupported enhanced drawing path; manual rendering required')
        if not tokens or tokens[0] != 'M':
            raise ValueError('Drawing path must start with moveto')
        command, count = None, 0
        arity = {'M':2, 'L':2, 'C':6, 'Q':4, 'Z':0}
        for token in tokens + ['M']:
            if token in arity:
                if command is not None and ((arity[command] and (not count or count % arity[command])) or (command == 'Z' and count)):
                    raise ValueError('Invalid drawing path coordinate count')
                command, count = token, 0
            else:
                if not math.isfinite(float(token)):
                    raise ValueError('Non-finite drawing coordinate')
                count += 1
        return ' '.join(tokens)


def render(shape, resolver):
    if shape.get(qn('draw','transform')):
        raise ValueError('Transformed drawing requires manual rendering to preserve diagram layout')
    properties = {}
    styles = [resolver.defaults.get('graphic')]
    styles += [resolver.styles.get(('graphic', name)) for name in reversed(list(resolver.chain(shape.get(qn('draw','style-name')), 'graphic')))]
    for style in styles:
        if style is not None:
            for child in style:
                properties.update(child.attrib)
    fill = properties.get(qn('draw','fill'), 'solid')
    stroke = properties.get(qn('draw','stroke'), 'solid')
    if fill not in {'solid','none'} or stroke not in {'solid','none'}:
        raise ValueError('Unsupported drawing paint effect; manual rendering required')
    if any(properties.get(qn('draw', key)) for key in ('marker-start','marker-end')):
        raise ValueError('Drawing with arrow markers requires manual rendering')
    svg = etree.Element(f'{{{SVG}}}svg', nsmap={None:SVG})
    for dimension in ('width','height'):
        svg.set(dimension, shape.get(f'{{{ODF_SVG}}}{dimension}', '1cm'))
    svg.set('preserveAspectRatio', 'none')
    svg.set('overflow', 'visible')
    geometry = shape.find('draw:enhanced-geometry', NS)
    if shape.tag == qn('draw','line'):
        points = {key:millimetres(shape.get(f'{{{ODF_SVG}}}{key}','0')) for key in ('x1','y1','x2','y2')}
        width = max(abs(points['x2']-points['x1']), 0.01)
        height = max(abs(points['y2']-points['y1']), 0.01)
        svg.set('width', f'{width:g}mm')
        svg.set('height', f'{height:g}mm')
        svg.set('viewBox', f"{min(points['x1'],points['x2']):g} {min(points['y1'],points['y2']):g} {width:g} {height:g}")
        node = etree.SubElement(svg, f'{{{SVG}}}line', **{k:f'{v:g}' for k,v in points.items()})
    elif shape.tag == qn('draw','rect'):
        if shape.get(qn('draw','corner-radius')):
            raise ValueError('Rounded drawing requires manual rendering')
        svg.set('viewBox', '0 0 100 100')
        node = etree.SubElement(svg, f'{{{SVG}}}rect', x='0', y='0', width='100', height='100')
    elif geometry is not None:
        if any(geometry.get(qn('draw', key), 'false') == 'true' for key in ('mirror-horizontal','mirror-vertical','extrusion')):
            raise ValueError('Mirrored or extruded drawing requires manual rendering')
        svg.set('viewBox', geometry.get(f'{{{ODF_SVG}}}viewBox', '0 0 21600 21600'))
        node = etree.SubElement(svg, f'{{{SVG}}}path', d=EnhancedPath(geometry).convert(geometry.get(qn('draw','enhanced-path'), '')))
        node.set('fill-rule', 'evenodd')
    else:
        raise ValueError('Missing enhanced drawing geometry; manual rendering required')
    node.set('fill', properties.get(qn('draw','fill-color'), '#000000') if fill != 'none' else 'none')
    node.set('stroke', properties.get(f'{{{ODF_SVG}}}stroke-color', '#000000') if stroke != 'none' else 'none')
    node.set('stroke-width', properties.get(f'{{{ODF_SVG}}}stroke-width', '0.01mm'))
    node.set('vector-effect', 'non-scaling-stroke')
    return svg
