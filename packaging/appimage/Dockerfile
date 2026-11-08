# syntax=docker/dockerfile:1
#
# Build a fully self-contained Resolve Ready AppImage on Ubuntu 22.04.
#
# Ubuntu 22.04 is intentional: the AppImage inherits its glibc (2.35), the
# minimum for Ubuntu 22.04+ and Debian 12+. The release is tested on Ubuntu
# 22.04/24.04/26.04 and Debian 12/13 on x86_64. Everything else (Python, GTK4,
# libadwaita, ffmpeg) is bundled.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    APPIMAGE_EXTRACT_AND_RUN=1 \
    LANG=C.UTF-8

# Bootstrap a current CA bundle first: the base image ships an old one and
# archive.ubuntu.com is HTTPS-only in many CI environments.
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list \
 && apt-get -o Acquire::https::Verify-Peer=false update \
 && apt-get -o Acquire::https::Verify-Peer=false install -y --no-install-recommends ca-certificates \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        file \
        nasm \
        patchelf \
        pkg-config \
        desktop-file-utils \
        squashfs-tools \
        zsync \
        xz-utils \
        libfuse2 \
        gtk-update-icon-cache \
        libglib2.0-bin \
        libgdk-pixbuf2.0-bin \
        librsvg2-common \
 && rm -rf /var/lib/apt/lists/*

# Build ffmpeg/ffprobe as small static binaries with only the codecs Resolve
# Ready needs.  --disable-gpl --disable-nonfree keeps the binaries LGPL, so the
# AppImage does not redistribute Ubuntu's GPL ffmpeg.  The exact source and
# configure line are recorded in THIRD_PARTY_NOTICES.md.
#
# Keep x86 assembly enabled.  FFmpeg 6.1.2's C-only 8-bit DNxHR path corrupts
# chroma and produces magenta/green bars; the SSE/AVX paths are correct.
RUN curl -fsSL --retry 3 -o /tmp/ffmpeg.tar.gz https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n6.1.2.tar.gz \
 && echo "9cbefd67b7e4fffde3846699ec03324b7ef789a81c2e9b1059e93719b5b8d189  /tmp/ffmpeg.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/ffmpeg.tar.gz -C /tmp \
 && cd /tmp/FFmpeg-n6.1.2 \
 && ./configure \
        --prefix=/opt/ffmpeg-static \
        --disable-everything \
        --disable-doc --disable-debug --disable-network --disable-autodetect \
        --disable-gpl --disable-nonfree --disable-version3 \
        --enable-ffmpeg --enable-ffprobe \
        --enable-avcodec --enable-avformat --enable-swscale --enable-swresample --enable-avfilter \
        --enable-protocol=file,pipe \
        --enable-demuxer=mov,matroska,avi,mpegts,mpegps,flv,ogg,mp3,wav,mxf \
        --enable-muxer=mov \
        --enable-decoder=aac,ac3,eac3,mp3,flac,opus,vorbis,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,pcm_alaw,pcm_mulaw,h264,hevc,mpeg2video,mpeg4,prores,dnxhd,vp8,vp9,av1,mjpeg,rawvideo \
        --enable-encoder=dnxhd,prores_ks,pcm_s24le,pcm_s16le,pcm_s32le \
        --enable-parser=aac,ac3,h264,hevc,mpeg4video,mpegvideo,vp8,vp9,av1 \
        --enable-filter=scale,format,aresample,anull,null,copy,setpts,asetpts,fps,trim,atrim,concat \
        --enable-bsf=h264_mp4toannexb,hevc_mp4toannexb \
        --extra-cflags=-O2 \
 && make -j"$(nproc)" \
 && make install \
 && mkdir -p /opt/ffmpeg-static/licenses \
 && cp COPYING.LGPLv2.1 COPYING.LGPLv3 /opt/ffmpeg-static/licenses/ \
 && rm -rf /tmp/FFmpeg-n6.1.2 /tmp/ffmpeg.tar.gz

# appimage-builder bundles its own Python runtime.
RUN curl -fsSL --retry 3 -o /opt/appimage-builder.AppImage \
        https://github.com/AppImageCrafters/appimage-builder/releases/download/v1.1.0/appimage-builder-1.1.0-x86_64.AppImage \
 && chmod +x /opt/appimage-builder.AppImage

COPY . /src
WORKDIR /work

ENTRYPOINT ["/bin/bash", "/src/packaging/appimage/build_inside.sh"]
