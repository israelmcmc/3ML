#!/usr/bin/env bash

# Make sure we fail in case of errors
set -e

# Copy sources (we do not have write permission on the mounted $TRAVIS_BUILD_DIR),
# so let's make a copy of the source code
cd ~
rm -rf my_work_dir
mkdir my_work_dir
# Copy also dot files (.*)
shopt -s dotglob
cp -R ${TRAVIS_BUILD_DIR}/* my_work_dir/

cd my_work_dir

# Get the version in the __version__ environment variable
python ci/set_minor_version.py --patch $TRAVIS_BUILD_NUMBER --version_file threeML/version.py

export PKG_VERSION=$(cd threeML && python -c "import version;print(version.__version__)")

echo "Building ${PKG_VERSION} ..."

# Update conda
conda update --yes -q conda #conda-build

# Answer yes to all questions (non-interactive)
conda config --set always_yes true

# We will upload explicitly at the end, if successful
conda config --set anaconda_upload no

# Make sure conda-forge is the first channel
conda config --add channels conda-forge


if [[ "$TRAVIS_OS_NAME" == "linux" ]]; then

    # in the hawc docker container we have a configuration file

    source ${SOFTWARE_BASE}/config_hawc.sh
    source activate test_env
    conda install -c conda-forge pytest codecov pytest-cov git --no-update-deps
else

    # Create and activate test environment on Mac

    conda create --name test_env -c conda-forge python=$TRAVIS_PYTHON_VERSION root5 pytest codecov pytest-cov git

    # Activate test environment
    source activate test_env

fi

# Build package
cd conda-dist/recipes/threeml
conda build -c conda-forge -c threeml --python=$TRAVIS_PYTHON_VERSION .

# Figure out where is the package
CONDA_BUILD_PATH=$(conda build . --output -c conda-forge -c threeml --python=2.7 | rev | cut -f2- -d"/" | rev)

# Install it
conda install --use-local -c conda-forge -c threeml threeml xspec-modelsonly-lite

# We re-install cthreeML to make sure that it uses versions of boost compatible
# with what is installed in the container
if [[ "$TRAVIS_OS_NAME" == "linux" ]]; then

    export CFLAGS="-m64 -I${CONDA_PREFIX}/include"
    export CXXFLAGS="-DBOOST_MATH_DISABLE_FLOAT128 -m64 -I${CONDA_PREFIX}/include"
    pip install git+https://github.com/giacomov/cthreeML.git --no-deps --upgrade

    # Make sure we can load the HAWC plugin
    python -c "from threeML.plugins.HAWCLike import HAWCLike"
    python -c "import os; print(os.environ['HAWC_3ML_TEST_DATA_DIR'])"

fi

# Run tests
cd ~/my_work_dir/threeML/test

# This is needed for ipyparallel to find the test modules
export PYTHONPATH=`pwd`:${PYTHONPATH}
python -m pytest --ignore=threeML_env -vv --cov=threeML

# Codecov needs to run in the main git repo

# Upload coverage measurements if we are on Linux
if [[ "$TRAVIS_OS_NAME" == "linux" ]]; then

    echo "********************************** COVERAGE ******************************"
    codecov -t 96594ad1-4ad3-4355-b177-dcb163cfc128

fi

# If we are on the master branch upload to the channel
if [[ "$TRAVIS_BRANCH" == "master" ]]; then

        conda install -c conda-forge anaconda-client
        anaconda -t $CONDA_UPLOAD_TOKEN upload -u threeml ${CONDA_BUILD_PATH}/threeml*.tar.bz2 --force

else

        echo "On a branch, not uploading to Conda channel"


fi
