# Rift

CECI EST UN TEST GERRITHUB

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
sudo -n dnf -y install rpmlint rpm-python3 python3-pylint python3-jinja2 \
    python3-nose platform-python-coverage python3-PyYAML python3-rpm \
    python3-dnf rpm-sign openssh-clients genisoimage qemu qemu-img
```

Run this command for static source code linting:


```sh
$ pylint-3 '--good-names=i,j,k,ex,Run,_,rc,vm' -d E1101 -d W0511 \
    --msg-template="$msg_template" lib/rift
```

Run this command to run unit tests:

```sh
$ export PYTHONPATH=$PWD/lib
$ nosetests-3.6 -vs --all-modules --with-xunit --with-coverage \
    --cover-package=rift --cover-xml tests
```

> [!IMPORTANT]
> Unit tests download virtual machine images from the Internet. The unit tests
> use the value of `https_proxy` environment variable as the Rift proxy
> configuration parameter, if this variable is defined in your environment. If
> you do not have direct access to Internet, you must define this environment
> variable with your network's proxy server to run the tests successfully.
