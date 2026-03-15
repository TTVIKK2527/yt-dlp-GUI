pkgname=yt-dlp-gui
pkgver=0.6.5
pkgrel=1
pkgdesc='Comprehensive desktop GUI for yt-dlp'
arch=('any')
url='https://github.com/yt-dlp/yt-dlp'
license=('MIT')
depends=('python' 'tk')
_ytdlp_tag='2026.03.13'
source=("https://github.com/yt-dlp/yt-dlp/releases/download/${_ytdlp_tag}/yt-dlp")
sha256sums=('SKIP')

package() {
  install -d "$pkgdir/usr/share/yt-dlp-gui"
  cp -r "$startdir/src" "$pkgdir/usr/share/yt-dlp-gui/src"
  cp -r "$startdir/assets" "$pkgdir/usr/share/yt-dlp-gui/assets"
  install -Dm755 "$srcdir/yt-dlp" "$pkgdir/usr/share/yt-dlp-gui/bin/yt-dlp"

  install -Dm755 "$startdir/packaging/yt-dlp-gui-launcher" "$pkgdir/usr/bin/yt-dlp-gui"
  install -Dm644 "$startdir/packaging/yt-dlp-gui.desktop" "$pkgdir/usr/share/applications/yt-dlp-gui.desktop"
  install -Dm644 "$startdir/assets/yt-dlp.ico" "$pkgdir/usr/share/pixmaps/yt-dlp-gui.ico"
  install -Dm644 "$startdir/assets/yt-dlp.png" "$pkgdir/usr/share/pixmaps/yt-dlp-gui.png"
  install -Dm644 "$startdir/assets/yt-dlp.png" "$pkgdir/usr/share/icons/hicolor/256x256/apps/yt-dlp-gui.png"
  install -Dm644 "$startdir/README.md" "$pkgdir/usr/share/doc/yt-dlp-gui/README.md"
}
