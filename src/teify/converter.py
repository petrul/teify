"""Run the pinned petrul/tei-stylesheets transform with a preservation profile."""
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
import shutil
import subprocess
from lxml import etree


@dataclass
class TEIConverter:
    stylesheets: Path = Path('vendor/tei-stylesheets')
    java: str = 'java'

    def check_available(self):
        self.stylesheets = self.stylesheets.resolve()
        for path in (self.stylesheets / 'odt/odttotei.xsl', self.stylesheets / 'lib/saxon9he.jar'):
            if not path.is_file():
                raise ValueError(f'Converter dependency missing: {path}; see README setup')
        if not shutil.which(self.java):
            raise ValueError(f'Java executable not found: {self.java}')

    def revision(self):
        result = subprocess.run(['git', '-C', str(self.stylesheets), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else 'unknown'

    def convert(self, source, destination):
        profile = etree.fromstring(files('teify').joinpath('resources/preserve-odf.xsl').read_bytes())
        profile[0].set('href', (self.stylesheets / 'odt/odttotei.xsl').as_uri())
        stylesheet = Path(source).parent / 'conversion-profile.xsl'
        etree.ElementTree(profile).write(str(stylesheet), encoding='utf-8', xml_declaration=True)
        result = subprocess.run([
            self.java, '-Xmx512m', '-jar', str(self.stylesheets / 'lib/saxon9he.jar'),
            f'-s:{Path(source).resolve()}', f'-xsl:{stylesheet.resolve()}', f'-o:{Path(destination).resolve()}',
        ], capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f'TEI stylesheet conversion failed:\n{result.stderr[-6000:]}')
        return result.stderr.strip()
