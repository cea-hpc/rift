%{?python_enable_dependency_generator}

%define version %{?ci_version}%{!?ci_version:$(python3 -c "from lib.rift import __version__; print(__version__)")}

Name:           rift
Version:        %{version}
Release:        1%{?dist}

License:        CeCILL-C
Source:         https://github.com/cea-hpc/rift/archive/refs/tags/v%{version}.tar.gz#/%{name}-%{version}.tar.gz
URL:            https://github.com/cea-hpc/rift

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
Summary:        Tool to build and maintain your own RPM based repository
BuildArch:      noarch
Requires:       createrepo_c
Requires:       genisoimage
Requires:       lftp
Requires:       openssh-clients
Requires:       python3-boto3
Requires:       python3-dnf
Requires:       python3-jinja2
Requires:       python3-PyYAML
Requires:       python3-requests
Requires:       python3-rpm
Requires:       qemu
Requires:       qemu-img
Requires:       qemu-user
Requires:       qemu-virtiofsd
Requires:       rpmlint
Requires:       rpm-sign

%description
Rift is a tool to manage RPM packages development effectively during their
complete lifecycle. It provides commands to perform the following actions:

* Creating new packages, either from scratch or imported from existing sources.
* Maintain and updates packages in YUM/DNF repositories.
* Launch and report automatic advanced integration and functional tests
  performed in sandboxed virtual machines for more isolation and more
  flexibility in the tests environments.

%prep
%autosetup

%build
%py3_build

%install
%py3_install

%files
%license Licence_CeCILL-C_V1-en.txt
%doc README.md
%doc AUTHORS
%doc Changelog
%{_bindir}/rift
%{python3_sitelib}/
%{_datadir}/%{name}

%changelog
