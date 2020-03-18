from __future__ import print_function
import io
import os
from setuptools import setup
import pyforked_daapd

here = os.path.abspath(os.path.dirname(__file__))


def read(*filenames, **kwargs):
    encoding = kwargs.get("encoding", "utf-8")
    sep = kwargs.get("sep", "\n")
    buf = []
    for filename in filenames:
        with io.open(filename, encoding=encoding) as f:
            buf.append(f.read())
    return sep.join(buf)


long_description = read("README.md")

setup(
    name="pyforked-daapd",
    version=pyforked_daapd.__version__,
    url="http://github.com/uvjustin/pyforked-daapd/",
    license=" ",
    author="Justin Wong",
    install_requires=[],
    author_email="46082645+uvjustin@users.noreply.github.com",
    description="Python Interface for forked-daapd",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=["pyforked_daapd"],
    include_package_data=True,
    platforms="any",
    classifiers=[
        "Programming Language :: Python",
        "Development Status :: 4 - Beta",
        "Natural Language :: English",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
