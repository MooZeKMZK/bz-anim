%global pypi_name bz-anim

Name:           bz-anim
Version:        %{?_version}%{!?_version:0.1.0}
Release:        1%{?dist}
Summary:        2D Belousov-Zhabotinsky reaction-diffusion simulator (CLI, Textual TUI, PySide6 GUI)
License:        MIT
URL:            https://github.com/MooZeKMZK/bz-anim
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel

Requires:       python3-bz-anim-core = %{version}-%{release}
Requires:       bz-anim-cli = %{version}-%{release}
Recommends:     bz-anim-tui = %{version}-%{release}
Recommends:     bz-anim-gui = %{version}-%{release}

%description
Umbrella package and unified dispatcher (bz-anim) for the 2D Belousov-Zhabotinsky
reaction-diffusion simulator with seamless temporal pulse-wipe looping, 2D torus
spatial tileability, and Ferroin 1D chemical color lookup tables.

%package -n python3-bz-anim-core
Summary:        Core 2D Belousov-Zhabotinsky simulation engine and TOML theme system
Requires:       python3 >= 3.10
Requires:       python3-numpy
Requires:       python3-pillow

%description -n python3-bz-anim-core
Core 2D Belousov-Zhabotinsky reaction-diffusion simulation engine, TOML config
loader, and Neo-Brutalist theme system.

%package -n bz-anim-cli
Summary:        Command-line interface (bz-cli) for the BZ reaction-diffusion simulator
Requires:       python3-bz-anim-core = %{version}-%{release}

%description -n bz-anim-cli
Command-line interface (bz-cli) for generating seamlessly looping, 2D torus-tileable
Belousov-Zhabotinsky reaction GIF animations.

%package -n bz-anim-tui
Summary:        Neo-Brutalist Textual terminal UI (bz-tui) for the BZ simulator
Requires:       python3-bz-anim-core = %{version}-%{release}
Requires:       bz-anim-cli = %{version}-%{release}
Recommends:     python3-textual

%description -n bz-anim-tui
Interactive Neo-Brutalist Textual terminal UI (bz-tui) with 2x4 Braille sub-pixel
rendering and live simulation controls.

%package -n bz-anim-gui
Summary:        Neo-Brutalist PySide6 desktop GUI (bz-gui) for the BZ simulator
Requires:       python3-bz-anim-core = %{version}-%{release}
Requires:       bz-anim-cli = %{version}-%{release}
Recommends:     python3-pyside6

%description -n bz-anim-gui
Interactive Neo-Brutalist PySide6 desktop GUI (bz-gui) with live viewport preview,
Ferroin 1D LUT, and GIF export.

%prep
%setup -q -n %{name}-%{version}

%build
for subpkg in core cli tui gui; do
  %{__python3} -m pip wheel --no-deps --no-build-isolation --wheel-dir "build_wheels/${subpkg}" "packages/${subpkg}"
done
%{__python3} -m pip wheel --no-deps --no-build-isolation --wheel-dir "build_wheels/umbrella" .

%install
rm -rf %{buildroot}
for subpkg in core cli tui gui umbrella; do
  %{__python3} -m pip install --no-deps --no-compile --root %{buildroot} --prefix %{_prefix} "build_wheels/${subpkg}"/*.whl
done

install -Dm644 config.toml %{buildroot}%{_sysconfdir}/bz-anim/config.toml
install -Dm644 theme.toml %{buildroot}%{_sysconfdir}/bz-anim/theme.toml
install -Dm644 packaging/desktop/bz-anim.desktop %{buildroot}%{_datadir}/applications/bz-anim.desktop
install -Dm644 packaging/desktop/bz-anim.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/bz-anim.svg

%files -n python3-bz-anim-core
%config(noreplace) %{_sysconfdir}/bz-anim/config.toml
%config(noreplace) %{_sysconfdir}/bz-anim/theme.toml
%{python3_sitelib}/bz_anim_core/
%{python3_sitelib}/bz_anim_core-*.dist-info/

%files -n bz-anim-cli
%{_bindir}/bz-cli
%{python3_sitelib}/bz_anim_cli/
%{python3_sitelib}/bz_anim_cli-*.dist-info/

%files -n bz-anim-tui
%{_bindir}/bz-tui
%{python3_sitelib}/bz_anim_tui/
%{python3_sitelib}/bz_anim_tui-*.dist-info/

%files -n bz-anim-gui
%{_bindir}/bz-gui
%{python3_sitelib}/bz_anim_gui/
%{python3_sitelib}/bz_anim_gui-*.dist-info/
%{_datadir}/applications/bz-anim.desktop
%{_datadir}/icons/hicolor/scalable/apps/bz-anim.svg

%files
%{_bindir}/bz-anim
%{python3_sitelib}/base.py
%{python3_sitelib}/cli.py
%{python3_sitelib}/tui.py
%{python3_sitelib}/gui.py
%{python3_sitelib}/theme.py
%{python3_sitelib}/bz_anim.py
%{python3_sitelib}/__pycache__/*
%{python3_sitelib}/bz_anim-*.dist-info/
