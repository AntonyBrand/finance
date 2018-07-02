with import<nixpkgs> {};
stdenv.mkDerivation rec {
  name = "env";
  env = buildEnv { name = name; paths = buildInputs; };
  buildInputs = [
  python3
  python36Packages.pip
  python36Packages.flask
  python36Packages.virtualenv
  python36Packages.pip
  python36Packages.sqlalchemy
  python36Packages.flask_sqlalchemy
  ];
  shellHook = ''
    export export FLASK_APP=application.py
    FLASK_DEBUG=1
    FLASK_ENV=development
    virtualenv --no-setuptools venv
    export PATH=$PWD/venv/bin:$PATH
    pip install -r requirements.txt
    '';
}
