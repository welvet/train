#!/usr/bin/env bash
# Continuous deployment loop: pull from git, run the backend, repeat on exit.

echo -e "\033[32mStarting continuous deployment loop...\033[0m"
echo -e "\033[33mPress Ctrl+C to stop\033[0m"
echo ""

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"

while true; do
    echo -e "\033[36m================================\033[0m"
    echo -e "\033[36mPulling latest changes from git...\033[0m"
    echo -e "\033[36m================================\033[0m"

    cd "$REPO_ROOT"

    pull_output=$(git pull 2>&1)
    pull_exit=$?

    echo "$pull_output"

    if [ $pull_exit -eq 0 ]; then
        echo ""
        echo -e "\033[32mGit pull successful!\033[0m"
        echo ""
        echo -e "\033[36m================================\033[0m"
        echo -e "\033[36mStarting backend server...\033[0m"
        echo -e "\033[36m================================\033[0m"
        echo ""

        cd "$BACKEND_DIR"

        source .venv/bin/activate 2>/dev/null
        pip install --index-url https://pypi.org/simple/ -e ".[dev]" -q

        python -m train 2>&1
        exit_code=$?

        echo ""
        if [ $exit_code -ne 0 ]; then
            echo -e "\033[31mBackend server failed with exit code $exit_code\033[0m"
        else
            echo -e "\033[33mBackend server stopped gracefully.\033[0m"
        fi
        echo -e "\033[33mRestarting loop...\033[0m"
        echo ""
    else
        echo ""
        echo -e "\033[31mGit pull failed! Waiting 5 seconds before retry...\033[0m"
        echo ""
        sleep 5
    fi
done
