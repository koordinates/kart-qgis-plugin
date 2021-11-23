# Contributing

We welcome all contributions, bug reports, and suggestions!

## Installing the development version

To install the latest version from this repository, follow these steps:

- Install [Kart](https://github.com/koordinates/kart)
- Clone this repository using `git clone`.

```console
$ git clone https://github.com/koordinates/kart-qgis-plugin.git
```

- Create a link between the repository folder and the QGIS 3 plugins folder.

```console
$ cd kart-qgis-plugn
$ python helper.py install
```

- Start QGIS and you will find the plugin in the plugins menu. If it's not available yet, activate
it in the QGIS Plugin Manager.


## Packaging

To package the plugin, suitable for installing into QGIS:

```console
$ python helper.py package
```

A `kart.zip` file is generated in the repo root.

## CI

Continuous integration builds an plugin package for every commit, artifacts are
[available to download](https://github.com/koordinates/kart-qgis-plugin/actions/workflows/build.yml).

## Code formatting

We use [Black](https://github.com/psf/black) to ensure consistent code formatting. We recommend integrating black with your editor:

* Sublime Text: install [sublack](https://packagecontrol.io/packages/sublack) via Package Control
* VSCode [instructions](https://code.visualstudio.com/docs/python/editing#_formatting)

We use the default settings, and target python 3.7+.

One easy solution is to install [pre-commit](https://pre-commit.com), run `pre-commit install --install-hooks` and it'll automatically validate your changes code as a git pre-commit hook.
