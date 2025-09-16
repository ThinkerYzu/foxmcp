if [ ! -e "../venv/bin/activate" ]; then
    echo "Please create a virtual environment in the '../venv' directory."
    exit 1
fi
source ../venv/bin/activate
export FOXMCP_EXT_SCRIPTS="$(pwd)/../predefined-ex/"
python ../server/server.py > foxmcp.log 2>&1 &

sleep 2
claude $*

kill %1
