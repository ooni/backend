# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "precise32"
  config.vm.box_url = "http://files.vagrantup.com/precise32.box"
  config.vm.synced_folder ".", "/data/oonib"
end

$setup_script = <<SCRIPT
set -e
apt-get update
apt-get -y install curl python-setuptools python-dev libsqlite3-dev libffi-dev

echo "Updating to the latest version of PIP"
cd /tmp/

curl --fail -O https://bootstrap.pypa.io/get-pip.py
python ./get-pip.py  ## pip (>=1.3.0) is recommended for security reasons

sudo update-alternatives --install /usr/bin/pip pip /usr/local/bin/pip 0

echo "Installing virtualenv and virtualenvwrapper..."

echo "Installing Tor..."

echo "deb http://deb.torproject.org/torproject.org precise main" >> /etc/apt/sources.list

gpg --keyserver keys.gnupg.net --recv 886DDD89
gpg --export A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89 | apt-key add -

apt-get update
apt-get -y install deb.torproject.org-keyring tor tor-geoipdb

cd /data/oonib

echo "Generating SSL keys"

openssl genrsa -out private.key 4096
openssl req -new -key private.key -out server.csr -subj '/CN=www.example.com/O=Example/C=AU'

openssl x509 -req -days 365 -in server.csr -signkey private.key -out certificate.crt

cp oonib.conf.example oonib.conf

echo "Installing oonib dependencies"
pip install -r requirements.txt

echo "Now:"
echo "1. vagrant ssh"
echo "2. cd /data/oonib"
echo "3. vi oonib.conf  # possibly"
echo "4. sudo ./bin/oonib"
SCRIPT

Vagrant.configure("2") do |config|
    config.vm.provision :shell, :inline => $setup_script
end
