#!/bin/sh

# This script installs necessary dependencies for a project, generates the prisma client and migrates the database, before starting up. The project directory, path depends on the project path.

PROJECT_DIR="/app/project"
REQUIRED_FILES="package.json vite.config.ts tsconfig.json"
CHECKSUM_FILE="node_modules/.checksums.md5"

# Variable to track the server process ID
SERVER_PID=""

# Function to get combined checksum of all monitored files
get_checksum() {
    {
        find . -maxdepth 1 -name "package.json" -type f -exec openssl md5 -r {} \; 2>/dev/null
        find . -maxdepth 1 -name ".env*" -type f -exec openssl md5 -r {} \; 2>/dev/null
    } | awk '{print $1}' | sort | openssl md5 -r 2>/dev/null | awk '{print $1}' || echo ""
}

# Function to read stored checksum
get_stored_checksum() {
    if [ -f "$CHECKSUM_FILE" ]; then
        cat "$CHECKSUM_FILE" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

# Function to update stored checksum
update_checksum() {
    checksum_value=$1
    if [ ! -d "node_modules" ]; then
        mkdir -p node_modules 2>/dev/null || true
    fi
    echo "$checksum_value" > "$CHECKSUM_FILE" 2>/dev/null || true
}

# Function to kill child processes of a given PID
kill_children() {
    parent_pid=$1
    signal=${2:-TERM}

    ps -o pid,ppid | awk -v ppid="$parent_pid" '$2 == ppid {print $1}' | while read -r child_pid; do
        kill -$signal "$child_pid" 2>/dev/null || true
    done
}

# Function to kill processes using a specific port
kill_port() {
    port=$1
    pids=$(lsof -ti:$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "Found processes still using port $port, killing..."
        for pid in $pids; do
            kill -KILL $pid 2>/dev/null || true
        done
    fi
}

# Function to stop server process and cleanup
stop_server() {
    if [ -z "$SERVER_PID" ]; then
        return
    fi

    echo "Waiting for existing server process (PID: $SERVER_PID) to be killed..."
    KILLED_PID=$SERVER_PID

    # Step 1: Gracefully kill children then parent
    kill_children "$SERVER_PID" "TERM"
    kill -TERM $SERVER_PID 2>/dev/null || true

    # Step 2: Wait for graceful shutdown with timeout
    timeout=10
    count=0
    while kill -0 $SERVER_PID 2>/dev/null && [ $count -lt $timeout ]; do
        sleep 1
        count=$((count + 1))
    done

    # Step 3: Force kill if still running
    if kill -0 $SERVER_PID 2>/dev/null; then
        echo "Process did not terminate gracefully, forcing kill..."
        kill_children "$SERVER_PID" "KILL"
        kill -KILL $SERVER_PID 2>/dev/null || true
        sleep 1
    fi

    # Step 4: Cleanup any orphaned processes on the port
    kill_port 5000

    echo "Previous server process (PID: $KILLED_PID) killed."
}

# Function to start/restart the server
start_server() {
    echo "Installing dependencies..."
    pnpm install || {
        echo "Warning: pnpm install failed, but continuing..."
    }

    # Stop existing server if running
    stop_server

    # Start new server instance
    echo "Starting server..."
    if [ -n "$START_COMMAND" ]; then
        echo "Running START_COMMAND: $START_COMMAND"
        eval "$START_COMMAND" || {
            echo "Warning: START_COMMAND ($START_COMMAND) failed, but continuing..."
        } &
    else
        echo "Running pnpm dev"
        pnpm dev || {
            echo "Warning: pnpm dev failed, but continuing..."
        } &
    fi

    SERVER_PID=$!
    if [ -n "$SERVER_PID" ]; then
        echo "Server started with PID: $SERVER_PID"
    else
        echo "Warning: Server start command may have failed, but continuing..."
    fi
}

# Consolidated main loop
FILES_FOUND=false
while true; do
    # Check for required files if not yet found
    if [ "$FILES_FOUND" = false ]; then
        missing_file=false
        if [ ! -d "$PROJECT_PATH" ]; then
            missing_file=true
        else
            for file in $REQUIRED_FILES; do
                if [ ! -f "$PROJECT_PATH/$file" ]; then
                    echo "File $file not found in $PROJECT_PATH, waiting..."
                    missing_file=true
                    break
                fi
            done
        fi

        if [ "$missing_file" = false ]; then
            echo "Project files found."
            FILES_FOUND=true
            echo "Syncing project files from ${PROJECT_PATH} to ${PROJECT_DIR}..."
            rsync -a --exclude 'node_modules' ${PROJECT_PATH}/ ${PROJECT_DIR} || {
                echo "Warning: rsync failed, but continuing..."
            }
            echo "Changing directory to ${PROJECT_DIR}..."
            cd ${PROJECT_DIR} || {
                echo "Error: Failed to change directory to ${PROJECT_DIR}"
                sleep 10
                continue
            }
            start_server
            update_checksum "$(get_checksum)"
            sleep 10
        else
            echo "Waiting for project files in '$PROJECT_PATH' to be created..."
            sleep 10
            continue
        fi
    fi

    # Monitor for changes after files are found
    if [ "$FILES_FOUND" = true ]; then
        rsync -a --exclude 'node_modules' ${PROJECT_PATH}/ ${PROJECT_DIR} || {
            echo "Warning: rsync failed during monitoring, but continuing..."
        }
        
        OLD_CHECKSUM=$(get_stored_checksum)
        NEW_CHECKSUM=$(get_checksum)
        
        if [ -n "$NEW_CHECKSUM" ] && [ "$OLD_CHECKSUM" != "$NEW_CHECKSUM" ]; then
            echo "Monitored files have changed. Server will be restarted."
            update_checksum "$NEW_CHECKSUM"
            start_server
        fi
        
        sleep 10
    fi
done