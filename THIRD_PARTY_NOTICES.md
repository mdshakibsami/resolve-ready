# Third-Party Notices

Resolve Ready's own source code is licensed under the [MIT License](LICENSE).
The application depends on, and the self-contained AppImage distributes,
third-party software under other licenses. This file records the components
that are most relevant to redistribution.

## FFmpeg in the AppImage

The AppImage includes a **static build of FFmpeg 6.1.2** (`ffmpeg` and
`ffprobe`) configured without GPL or non-free components:

```
--disable-gpl --disable-nonfree --disable-version3
```

The build uses only FFmpeg's LGPL-compatible codecs and filters. It is
distributed under the **GNU Lesser General Public License, version 2.1 or
later**. The license texts are included in the AppImage at:

```
/usr/share/doc/resolve-ready/ffmpeg/COPYING.LGPLv2.1
/usr/share/doc/resolve-ready/ffmpeg/COPYING.LGPLv3
```

The FFmpeg project is at <https://ffmpeg.org/>. The exact source used for the
release is the upstream `n6.1.2` tree:

- Source archive:
  <https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n6.1.2.tar.gz>
- SHA-256:
  `9cbefd67b7e4fffde3846699ec03324b7ef789a81c2e9b1059e93719b5b8d189`
- The complete configure and build command is in
  [`packaging/appimage/Dockerfile`](packaging/appimage/Dockerfile).

The maintainers will provide the complete corresponding source for the bundled
FFmpeg build on request through
[GitHub Issues](https://github.com/mdshakibsami/resolve-ready/issues) for at least
three years after the release date. The upstream archive above, combined with
the build recipe in this repository, is sufficient to reproduce the binaries.

FFmpeg is invoked as a separate executable. The MIT license covers Resolve
Ready's own code; it does not relicense FFmpeg or its dependencies.

## GTK, libadwaita, Python and other AppImage components

The AppImage bundles Ubuntu 22.04 packages for Python 3.10, PyGObject, GTK 4.6,
libadwaita 1.1, GdkPixbuf, Adwaita icons, fontconfig, shared-mime-info and
their runtime dependencies. These components are distributed under their own
licenses (typically LGPL, MIT, BSD or similar). Their Debian copyright files
are included in the AppImage under `/usr/share/doc/<package>/copyright`.

The `.deb` package does **not** bundle these libraries or FFmpeg. It declares
dependencies on the distribution's packages, which are installed and licensed
by the user's distribution.

## Assets

The application icon and screenshot in `assets/` are original project assets
and are covered by the MIT License. The Adwaita icon theme used at runtime is a
separate third-party work with its own license and is not relicensed here.

## No warranty

All third-party components are provided "as is", without warranty of any kind,
to the extent permitted by their licenses.
