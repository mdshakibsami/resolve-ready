PYTHON ?= python3
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' src/resolve_ready/__init__.py | head -n 1)

.PHONY: test validate deb appimage verify-appimage clean

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

validate:
	desktop-file-validate assets/io.github.mdshakibsami.ResolveReady.desktop
	appstreamcli validate --no-net assets/io.github.mdshakibsami.ResolveReady.metainfo.xml

deb:
	./packaging/build_deb.sh

appimage:
	./packaging/build_appimage.sh

verify-appimage:
	./packaging/verify_appimage.sh dist/ResolveReady-$(VERSION)-x86_64.AppImage

clean:
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache htmlcov
