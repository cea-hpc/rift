#cloud-config

bootcmd:
 - cloud-init-per once delpasswd passwd -d root

#package_upgrade: true

ssh_pwauth: true

write_files:
  - path: /etc/yum/pluginconf.d/fastestmirror.conf
    permissions: '0644'
    content: |
        [main]
        enabled=0
  - path: /etc/yum/pluginconf.d/priorities.conf
    permissions: '0644'
    content: |
        [main]
        enabled = 1
        check_obsoletes = 1
  - path: /etc/dracut.conf.d/hostonly.conf
    permissions: '0644'
    content: |
        hostonly="yes"

ssh_pwauth: true

runcmd:
  - rm /root/firstrun       # For CentOS6
  - sed -i 's/^.*PermitRootLogin .*$/PermitRootLogin yes/' /etc/ssh/sshd_config  # For CentOS6
  - sed -i 's/^.*PermitEmptyPasswords .*$/PermitEmptyPasswords yes/' /etc/ssh/sshd_config
  - yum remove -y cloud-init
  - sed -i '/^HWADDR=/d' /etc/sysconfig/network-scripts/ifcfg-eth0
  - "# Do not disable SELinux for now # sed -i 's/^SELINUX=.*/SELINUX=disabled/' /etc/sysconfig/selinux"
  - "# For CentOS6"
  - sed -i '/^HOSTNAME=/d' /etc/sysconfig/network
  - service sshd restart
  - "# For CentOS7"
  - rm /etc/hostname
  - systemctl restart sshd
  - /bin/true

write_files:
  - path: '/root/.bashrc'
    content: |
        # .bashrc

        # User specific aliases and functions

        alias rm='rm -i'
        alias cp='cp -i'
        alias mv='mv -i'

        # Source global definitions
        if [ -f /etc/bashrc ]; then
                . /etc/bashrc
        fi
{%- if proxy is not none %}
        export https_proxy="{{ proxy }}"
        export http_proxy="{{ proxy }}"
        export ftp_proxy="{{ proxy }}"
{%- endif %}
        export no_proxy="{{ no_proxy }}"
