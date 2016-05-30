# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/precise32"

  # Create a forwarded port mapping which allows access to a specific port
  # within the machine from a port on the host machine. In the example below,
  # accessing "localhost:8080" will access port 80 on the guest machine.
  config.vm.network :forwarded_port, guest: 57001, host: 57001
  config.vm.network :forwarded_port, guest: 57001, host: 57002
  config.vm.network :forwarded_port, guest: 57001, host: 57003
  config.vm.network :forwarded_port, guest: 57004, host: 57004
  config.vm.network :forwarded_port, guest: 57005, host: 57005
  config.vm.network :forwarded_port, guest: 57006, host: 57006
  config.vm.network :forwarded_port, guest: 57007, host: 57007

  # Create a private network, which allows host-only access to the machine
  # using a specific IP.
  # config.vm.network :private_network, ip: "192.168.33.10"

  # Create a public network, which generally matched to bridged network.
  # Bridged networks make the machine appear as another physical device on
  # your network.
  # config.vm.network :public_network

  # Share an additional folder to the guest VM. The first argument is
  # the path on the host to the actual folder. The second argument is
  # the path on the guest to mount the folder. And the optional third
  # argument is a set of non-required options.
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
