# Contributing

We welcome all contributions, bug reports, and suggestions!

## Installing the development version

To install the latest version from this repository, follow these steps:

- Clone this repository using `git clone`.

```console
$ git clone https://github.com/koordinates/kart-qgis-plugin.git
```
- Move to the `kart-qgis-plugin` folder and run the helper install task by running

```console
$ python helper.py install
```

That will create a symlink between the repository folder and the QGIS 3 plugins folder.

- Start QGIS and you will find the plugin in the plugins menu. If it's not available yet, activate it in the QGIS Plugin Manager.


## Packaging

To package the plugin, run the helper package task by running

```console
$ python helper.py install
```

A `kart.zip` file is generated in the repo root.

## CI

Continuous integration builds an install package for every commit. Artifacts are published to Github Actions.

## Code formatting

We use [Black](https://github.com/psf/black) to ensure consistent code formatting. We recommend integrating black with your editor:

* Sublime Text: install [sublack](https://packagecontrol.io/packages/sublack) via Package Control
* VSCode [instructions](https://code.visualstudio.com/docs/python/editing#_formatting)

We use the default settings, and target python 3.7+.

One easy solution is to install [pre-commit](https://pre-commit.com), run `pre-commit install --install-hooks` and it'll automatically validate your changes code as a git pre-commit hook.
