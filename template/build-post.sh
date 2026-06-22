#!/bin/bash

set -x
set -e

echo '> Fetching Vm kernel version...'
uname -r

# When RIFT_KERNEL is defined (mapped to project's vm>kernel configuration
# parameter, install this specific kernel from cloud image default package
# repositories and pin this kernel as default entry in bootloader.
if [ -n "${RIFT_KERNEL}" ]; then
    echo "> Installing kernel ${RIFT_KERNEL}..."
    dnf install -y "kernel-${RIFT_KERNEL}"
    VMLINUZ=$(ls /boot/vmlinuz-*"${RIFT_KERNEL}"* 2>/dev/null | head -1)
    if [ -z "${VMLINUZ}" ]; then
        echo "Unable to find vmlinuz for kernel ${RIFT_KERNEL}"
        exit 1
    fi
    grubby --set-default "${VMLINUZ}"
fi

echo '> Fetching Vm repositories...'
grep '^\[' /etc/yum.repos.d/*

echo '> Disable default repositories'
for repo in $(grep "^\[" /etc/yum.repos.d/CentOS* /etc/yum.repos.d/alma* /etc/yum.repos.d/Rocky* -h | sed -e "s/\]\|\[//g"); do
    dnf config-manager --disable $repo
    echo "    * $repo - disabled"
done

if [ -n "${RIFT_ADDITIONAL_RPMS}" ]; then
  RPM_NAMES=$(echo ${RIFT_ADDITIONAL_RPMS}| tr ':' ' ')
  echo '> Installing provided RPMS...'
  cd /tmp
  ls -atl
  rpm -Uvh $RPM_NAMES
  rm $RPM_NAMES
  test $? || exit 1
fi

if [ ${RIFT_SHARED_FS_TYPE} = "9p" ] ; then
    echo '> Checking 9p modules...'
    modinfo 9pnet_virtio
    echo '> Loading 9p kernel module...'
    modprobe 9pnet_virtio
fi

echo '> Yum update...'
yum -y update || true

echo '> Yum cleaning...'
yum clean all
rm -f /var/log/yum.log
