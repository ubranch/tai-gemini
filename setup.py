from setuptools import setup, find_packages


setup(
    name="terminal-ai-assistant",
    version="4.2.0",
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
        "grpcio",
        "grpcio-tools",
        "protobuf",
    ],
    entry_points={"console_scripts": ["tai=tai.cli:main"]},
)
