# Rift

Rift is a tool to manage RPM packages development effectively during their
complete lifecycle. It provides commands to perform the following actions:

- Creating new packages, either from scratch or imported from existing sources.
- Maintain and updates packages.
- Launch and report automatic advanced integration and functional tests.

The tests are performed in virtual machines for more isolation and provide more
flexibility in the tests environments.

## Tests

To run the unit tests and static analysis, some dependencies are required:

```sh
$ dnf -y install python3-pip python3-jinja2 python3-PyYAML python3-rpm python3-dnf python3-pytest python3-pytest-cov sudo rpm-sign rpmlint openssh-clients genisoimage qemu qemu-user qemu-img qemu-virtiofsd mock createrepo_c python3-yaml python3-xmltodict python3-boto3 pylint
```

We recommand the use of [Fedora](https://fedoraproject.org) as developpement environnement.

Run this command for static source code linting:

```sh
$ pylint lib/rift
```

Run this command to run unit tests:

```sh
$ pytest
```

Pytest is configured in [pyproject.toml](./pyproject.toml) and in [pytest.ini](pytest.ini) files.

> [!IMPORTANT]
> Unit tests download virtual machine images from the Internet. The unit tests
> use the value of `https_proxy` environment variable as the Rift proxy
> configuration parameter, if this variable is defined in your environment. If
> you do not have direct access to Internet, you must define this environment
> variable with your network's proxy server to run the tests successfully.

