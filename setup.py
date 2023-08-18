from setuptools import setup, find_packages
from pathlib import Path


def load_requirements(fname: Path):
    reqs = []
    with fname.open('r') as reqs_file:
        for line in reqs_file:
            reqs.append(line.rstrip())
    return reqs


setup(
    name='mrcepid_testing',
    version='1.0.3',
    packages=find_packages(),
    url='https://github.com/mrcepid-rap/mrcepid-testing',
    license='MIT',
    author='Eugene Gardner',
    author_email='eugene.gardner@mrc-epid.cam.ac.uk',
    description='Testing suite for MRC-EPID',
    install_requires=load_requirements(Path('requirements.txt'))
)
