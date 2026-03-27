config_opts.setdefault('plugin_conf', {})
config_opts['plugin_conf']['ccache_enable'] = False
config_opts['root'] = '{{ name }}'
config_opts['target_arch'] = '{{ arch }}'
config_opts['legal_host_arches'] = ('{{ arch }}',)
config_opts['chroot_setup_cmd'] = 'groupinstall base development'
config_opts['dist'] = 'el6'  # only useful for --resultdir variable subst

config_opts['yum.conf'] = """
[main]
cachedir=/var/cache/yum
debuglevel=1
reposdir=/dev/null
logfile=/var/log/yum.log
retries=20
obsoletes=1
gpgcheck=0
assumeyes=1
syslog_ident=mock
syslog_device=

# repos
{% for repo in repos %}
[{{ repo.name }}]
name={{ repo.name }}
baseurl={{ repo.url }}
priority={{ repo.priority }}
enabled={% if 'main' in repo.variants %}1{% else %}0{% endif %}
{% if repo.module_hotfixes %}
module_hotfixes={{ repo.module_hotfixes }}
{% endif %}
{% if repo.proxy and not repo.authenticated %}
proxy={{ repo.proxy }}
{% endif %}
{% endfor %}
"""
