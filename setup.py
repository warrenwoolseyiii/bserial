from setuptools import setup, find_packages
from src.bserial.version import get_version

setup(
    name='bserial',
    version=get_version(),
    author='Warren Woolsey',
    description='Cross-platform serial port utility',
    url='https://github.com/warrenwoolseyiii/bserial',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    install_requires=[
        'pyserial',  # Required for serial communication
    ],
    python_requires='>=3.7',
    entry_points={
        'console_scripts': [
            'bserial=bserial.bserial:main',
        ],
    },
)
