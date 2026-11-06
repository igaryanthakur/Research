# Headless Agent JavaScript SDK Documentation

## Overview

The **Headless Agent JavaScript SDK** allows you to build custom chat interfaces and integrate agent conversations into any application without using the built-in chat widget. The SDK provides a simplified, headless API that handles socket connections, real-time agent events, and file uploads automatically.

-   **Base URL:** `<server-url>`
-   **Runtime:** Browser (JavaScript/TypeScript). Works with any framework (React, Vue, vanilla JS) or plain HTML.
-   **Entry point:** `createHeadlessAgentInstance(params)` — returns an instance with `emit()`, `on()`, and `cleanup()` methods.

<version-section>---

## Installation

When using a bundler (e.g. Vite, Webpack):

```bash
npm install @uptiqai/widgets-sdk<sdk-version-install>
# or
yarn add @uptiqai/widgets-sdk<sdk-version-install>
```

Then import the headless agent function:

```javascript
import { createHeadlessAgentInstance } from '@uptiqai/widgets-sdk';
```

For TypeScript projects, also import the types:

```typescript
import { createHeadlessAgentInstance } from '@uptiqai/widgets-sdk';
import type { HeadlessAgentInstance, AgentInterruptEvent } from '@uptiqai/widgets-sdk';
```

---

## Authentication & Authorization

The SDK authenticates using the **Agent Widget Key**. All communication with the backend (socket and REST) uses this key. Your application's domain must be whitelisted for the agent.

### Obtaining Your Widget Key

1. Go to your agent's **Agent Config Panel**.
2. Open the **Authentication** tab.
3. Create and copy your **Widget Key**.

This Widget Key is passed in the `config` object when creating an instance.

### Whitelisting Your Application Domain

The backend allows requests only from whitelisted origins. You must add your application's domain before the SDK can connect.

1. Go to your agent's **Agent Config Panel**.
2. Open the **Whitelisted Domains** tab.
3. Add and save your **Domain**:
    - **Full URL with protocol**: `https://app.example.com` or `http://localhost:5173`
    - **OR hostname only**: `localhost` or `app.example.com`
    - **Important**: No trailing spaces! Whitelist entries must match exactly.

If your domain is not whitelisted, socket connection or API calls will be rejected with an "unauthorized" error.

---

## Creating an Instance

### Method

```javascript
import { createHeadlessAgentInstance } from '@uptiqai/widgets-sdk';

const instance = createHeadlessAgentInstance({
    config: { serverUrl, agentId, widgetKey, agentExecutorVersion },
    user: { uid, firstName, lastName, email },
    instanceId: 'unique-instance-id'
});
```

### Get Agent config

1. find agent config for that agent from AGENT_CONFIGS (import from agentSdk/agent.ts)
2. using that config make request to get agentExecutorVersion

```javascript
const agentApi = axios.create({
    baseURL: import.meta.env.VITE_AGENT_BASE_URL,
    headers: { 'Content-Type': 'application/json' }
});

const agentResponse = await agentApi.get(`/agent-executor/agents/${agentId}`, {
    headers: {
        'app-id': config.appId,
        'account-id': config.accountId,
        'widgetkey': config.widgetKey
    }
});
const agent = agentResponse.data?.data;
const agentExecutorVersion = agent?.config?.agentExecutorVersion;
```

### Parameters

| Name         | Type           | Required | Description                                                   |
| ------------ | -------------- | -------- | ------------------------------------------------------------- |
| `config`     | `WidgetConfig` | Yes      | Backend and agent configuration. See Config Object below.     |
| `user`       | `WidgetUser`   | Yes      | Current user identity. See User Object below.                 |
| `instanceId` | `string`       | Yes      | Unique identifier for this instance (used for socket scoping) |

### Config Object

| Property               | Type     | Required | Description                                                 |
| ---------------------- | -------- | -------- | ----------------------------------------------------------- |
| `serverUrl`            | `string` | Yes      | Base URL of the Uptiq/Samuel backend (e.g. `<server-url>`). |
| `agentId`              | `string` | Yes      | Unique identifier of the agent (e.g. `<agent-id>`).         |
| `widgetKey`            | `string` | Yes      | Widget key from Agent Config → Authentication.              |
| `agentExecutorVersion` | `string` | No       | Executor version from agent config (optional).              |

### User Object

| Property    | Type     | Required | Description             |
| ----------- | -------- | -------- | ----------------------- |
| `uid`       | `string` | Yes      | Unique user identifier. |
| `firstName` | `string` | Yes      | User's first name.      |
| `lastName`  | `string` | No       | User's last name.       |
| `email`     | `string` | Yes      | User's email address.   |

### Example

```javascript
import { createHeadlessAgentInstance } from '@uptiqai/widgets-sdk';

const instance = createHeadlessAgentInstance({
    config: {
        serverUrl: import.meta.env.VITE_AGENT_BASE_URL, 
        agentId: 'c8f3ee71-ca26-428a-9761-c0011c441477',
        widgetKey: 'YOUR_AGENT_WIDGET_KEY',
        agentExecutorVersion: '<executor-version>'
    },
    user: {
        uid: 'user-123',
        firstName: 'Jane',
        lastName: 'User',
        email: 'jane@example.com'
    },
    instanceId: 'my-chat-instance'
});
```

---

## Instance API

The object returned by `createHeadlessAgentInstance` provides three methods:

### Methods

| Method                 | Type                                                | Description                                               |
| ---------------------- | --------------------------------------------------- | --------------------------------------------------------- |
| `emit(event, payload)` | `(event: 'query', payload: QueryPayload) => void`   | Send a query to the agent with optional file attachments. |
| `on(event, handler)`   | `(event: 'agent-interrupt', handler) => () => void` | Subscribe to agent events. Returns unsubscribe function.  |
| `cleanup()`            | `() => void`                                        | Clean up resources (remove listeners, disconnect socket). |

---

## Sending Messages: `emit('query', payload)`

### Description

Sends a user message to the agent and optionally attaches files. The SDK handles socket connection, file uploads, and message delivery automatically.

### Query Payload

| Property      | Type     | Required | Description                                                                    |
| ------------- | -------- | -------- | ------------------------------------------------------------------------------ |
| `content`     | `string` | Yes      | The user's message text (use `' '` if sending only files).                     |
| `executionId` | `string` | No       | Existing conversation/execution ID to continue a conversation.                 |
| `files`       | `File[]` | No       | Browser `File` objects to upload and attach (e.g. from `<input type="file">`). |

### File Upload Handling

When you pass `files`:

1. The SDK automatically obtains presigned upload URLs from the backend
2. Each file is uploaded directly to cloud storage (S3, etc.)
3. The file metadata is attached to the message sent to the agent

You don't need to handle file uploads manually—just pass the `File` objects.

### Examples

**New conversation:**

```javascript
instance.emit('query', {
    content: 'Hello, can you help me?'
});
```

**With file attachments:**

```javascript
instance.emit('query', {
    content: 'Analyze these documents',
    files: [file1, file2]
});
```

**Continue existing conversation:**

```javascript
instance.emit('query', {
    content: 'Tell me more about the second point',
    executionId: 'existing-execution-uuid'
});
```

**Files only (no text message):**

```javascript
instance.emit('query', {
    content: ' ',
    files: [selectedFile]
});
```

---

## Receiving Agent Events: `on('agent-interrupt', handler)`

### Description

Subscribe to agent events to receive messages, status updates, errors, and completion signals. The handler receives an `AgentInterruptEvent` that contains information about what the agent is doing.

### Event Handler

```typescript
const unsubscribe = instance.on('agent-interrupt', (event: AgentInterruptEvent) => {
    // Handle event based on event.type
});
```

The handler receives events with different `type` values. Use the `type` field to determine what to display.

### Event Types

| Event Type      | Description                | Key Fields                             |
| --------------- | -------------------------- | -------------------------------------- |
| `agent_message` | Agent text response        | `content` (string), `subtype` (string) |
| `status_update` | Progress indicator         | `status` (string)                      |
| `done`          | Execution completed        | `content` (optional string)            |
| `error`         | Error occurred             | `error` (string)                       |
| `tool_call`     | Agent is calling a tool    | Tool invocation details                |
| `tool_result`   | Tool call completed        | Tool result                            |
| `plan_update`   | Agent created/updated plan | Plan details                           |

### Important: Handling Agent Messages

Agent messages have a `subtype` field that indicates the message type:

-   `'intermediate'` - Streaming/partial message (shown during generation)
-   `'final'` - Complete message (shown when generation is complete)
-   `'question'` - Agent asking a question (requires user response)
-   `'final_stream'` - Final streaming chunk
-   `'output_files'` - Agent generated files
-   `'ask_permission'` - Agent requesting permission

**Handle multiple subtypes to avoid missing messages:**

```javascript
if (event.type === 'agent_message' && event.content) {
    // Handle different message subtypes
    if (event.subtype === 'final' || event.subtype === 'question' || event.subtype === 'final_stream') {
        // Display this message (complete responses and questions)
    } else if (event.subtype === 'intermediate') {
        // Update streaming message (optional - for real-time updates)
    }
}
```

**Important**: Don't filter only by `subtype === 'final'` or you'll miss agent questions and other message types!

### Example: Basic Event Handler

```javascript
instance.on('agent-interrupt', event => {
    switch (event.type) {
        case 'agent_message':
            // Handle different message subtypes
            if (['final', 'question', 'final_stream'].includes(event.subtype) && event.content) {
                displayMessage({ role: 'agent', content: event.content });
            }
            break;

        case 'error':
            displayMessage({ role: 'system', content: event.error || 'An error occurred' });
            break;

        case 'status_update':
            event.status;
            break;

        case 'done':
            'Execution completed';
            break;

        case 'tool_call':
            event.toolName;
            break;

        case 'tool_result':
            event.toolName;
            break;

        case 'plan_update':
            'Plan updated';
            break;

        default:
            console.log('Unknown event type:', event.type);
    }
});
```

---

## Cleanup

Always call `cleanup()` when you're done with the instance (e.g., when your component unmounts):

```javascript
instance.cleanup();
```

This removes event listeners and properly manages the socket connection.

---

## React Integration Example

Here's how to integrate the SDK into a React component:

```typescript
import { createHeadlessAgentInstance } from '@uptiqai/widgets-sdk';
import type { HeadlessAgentInstance, AgentInterruptEvent } from '@uptiqai/widgets-sdk';
import { useEffect, useRef, useState } from 'react';



const config = {
    serverUrl: 'http://app.localhost:3000',
    agentId: 'your-agent-id',
    widgetKey: 'your-widget-key',
    agentExecutorVersion: '<executor-version>'
};

const user = {
    uid: 'user-123',
    firstName: 'Jane',
    lastName: 'User',
    email: 'jane@example.com'
};

export const ChatComponent = () => {
    const [messages, setMessages] = useState<Array<{ role: 'user' | 'agent'; content: string }>>([]);
    const instanceRef = useRef<HeadlessAgentInstance | null>(null);

    useEffect(() => {
        // 1. Create headless agent instance
        const instance = createHeadlessAgentInstance({
            config,
            user,
            instanceId: 'my-chat-instance'
        });
        instanceRef.current = instance;

        // 2. Subscribe to agent events
        const unsubscribe = instance.on('agent-interrupt', (event: AgentInterruptEvent) => {
            switch (event.type) {
                case 'agent_message': {
                    const agentMsg = event as { content?: string; subtype?: string };
                    // Handle final messages, questions, and final streams
                    if (['final', 'question', 'final_stream'].includes(agentMsg.subtype || '') && agentMsg.content) {
                        setMessages(prev => [...prev, { role: 'agent', content: agentMsg.content! }]);
                    }
                    break;
                }

                case 'error': {
                    const errorMsg = (event as { error?: string }).error ?? 'An error occurred';
                    setMessages(prev => [...prev, { role: 'agent', content: errorMsg }]);
                    break;
                }

                case 'status_update':
                case 'done':
                case 'tool_call':
                case 'tool_result':
                case 'plan_update':
                    // Log these events (optional - add UI handling as needed)
                    console.log(`Event: ${event.type}`);
                    break;

                default:
                    console.log('Unknown event type:', event.type);
            }
        });

        // 3. Cleanup on unmount
        return () => {
            unsubscribe();
            instance.cleanup();
        };
    }, []);

    const sendMessage = (text: string, files?: File[]) => {
        // Add user message to UI
        setMessages(prev => [...prev, { role: 'user', content: text }]);

        // Send to agent
        instanceRef.current?.emit('query', {
            content: text,
            files: files
        });
    };

    return (
        <div>
            {/* Your UI here */}
            {messages.map((msg, i) => (
                <div key={i}>
                    {msg.role}: {msg.content}
                </div>
            ))}
        </div>
    );
};
```

### Key Implementation Details

1. **Instance Creation**: Create once in `useEffect` with empty dependencies
2. **Event Handling**: Handle multiple subtypes (`final`, `question`, `final_stream`) to capture all agent responses
3. **Cleanup**: Always call `unsubscribe()` and `instance.cleanup()` on unmount
4. **Sending Messages**: Use `instance.emit('query', { content, files? })` to send queries
5. **File Support**: Pass `File` objects directly—the SDK handles uploads automatically
6. **Execution ID**: The SDK automatically subscribes to socket events for the execution ID when you send a query

---

## TypeScript Types

The SDK exports the following TypeScript types:

```typescript
import type {
    HeadlessAgentInstance,
    QueryPayload,
    AgentInterruptEvent,
    CreateHeadlessAgentInstanceParams
} from '@uptiqai/widgets-sdk';
```

### Type Definitions

**HeadlessAgentInstance:**

```typescript
type HeadlessAgentInstance = {
    emit: (event: 'query', payload: QueryPayload) => void;
    on: (event: 'agent-interrupt', handler: (event: AgentInterruptEvent) => void) => () => void;
    cleanup: () => void;
};
```

**QueryPayload:**

```typescript
type QueryPayload = {
    content: string;
    executionId?: string;
    files?: File[];
};
```

**CreateHeadlessAgentInstanceParams:**

```typescript
type CreateHeadlessAgentInstanceParams = {
    config: {
        serverUrl: string;
        agentId: string;
        widgetKey: string;
        agentExecutorVersion?: string;
    };
    user: {
        uid: string;
        firstName: string;
        lastName?: string;
        email: string;
    };
    instanceId: string;
};
```

---

## Summary Reference

| Task                      | API                                                                 |
| ------------------------- | ------------------------------------------------------------------- |
| Create headless instance  | `createHeadlessAgentInstance({ config, user, instanceId })`         |
| Send user message         | `instance.emit('query', { content, executionId?, files? })`         |
| Receive agent updates     | `instance.on('agent-interrupt', (event) => { ... })`                |
| Show final agent messages | Check `event.type === 'agent_message' && event.subtype === 'final'` |
| Show errors               | Check `event.type === 'error'` → use `event.error`                  |
| Upload files              | Pass `files` array in query payload                                 |
| Unsubscribe               | Call the function returned by `on()`                                |
| Clean up resources        | Call `instance.cleanup()`                                           |

---

## Best Practices

1. **Single Instance**: Create one instance per chat context and reuse it for the entire conversation
2. **Handle Multiple Subtypes**: Check for `final`, `question`, and `final_stream` subtypes to capture all agent messages (not just `final`)
3. **Cleanup**: Always call `cleanup()` when unmounting to prevent memory leaks
4. **File Handling**: Let the SDK handle file uploads—just pass the `File` objects
5. **Error Handling**: Display error events to inform users when something goes wrong
6. **Execution ID**: Store and pass `executionId` to continue conversations across page reloads
7. **Domain Whitelisting**: Ensure exact matches with no trailing spaces (use full URL with protocol or hostname only)

---

## Operational Notes

-   The SDK automatically manages socket connections and reconnection
-   File uploads are handled automatically via presigned URLs
-   The socket connection is shared across multiple instances if they use the same user and config
-   Always subscribe to events before sending queries to ensure you don't miss any responses
-   For server-side or backend-only headless execution (no browser), use the REST API instead

This documentation reflects the current implementation of the Headless Agent JavaScript SDK and serves as the authoritative reference for building custom chat interfaces.
