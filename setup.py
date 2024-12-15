from setuptools import setup, find_packages


setup(
    name="terminal-ai-assistant",
    version="4.1.3",
    description="tAI, a terminal AI assistant, inspired by the movie 'The Terminal'",
    author="Inspire",
    author_email="unknown.branch@gmail.com",
    packages=find_packages(),
    package_data={
        "tai": ["prompt.md"],
    },
    install_requires=[
        "google-generativeai",
        "rich",
        "grpcio==1.60.1",
        "grpcio-tools>=1.59.0",
        "protobuf>=4.25.1",
    ],
    entry_points={"console_scripts": ["tai=tai.cli:main"]},
)
