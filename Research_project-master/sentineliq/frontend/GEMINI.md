## Prototyping Strategy & Mindset

- Think very very less, Don't plan, Directly work faster on implementation within seconds strictly.
- Remember to build only 3-4 simple features in one go for prototyping MVP.
- Before starting always read attached images, files if provided.
- **Image references = design inspiration, not layout blueprint.** When an image reference is provided, treat it as a design language guide. Extract design attributes (color palette, typography style, spacing density, component shape language, visual hierarchy) and use them to inspire the generated UI. Maintain originality in layout and component structure; adapt intelligently to the app's functional requirements.
- **Do not replicate the reference exactly.** Use it only for design inspiration (colors, typography, spacing, etc.); keep layout and structure original and suited to the app.
- Keep things simple and Clean. Don't do any complex implementations unless absolutely necessary.
- Don't add any complex libraries for animation, simulating backend/ai repospense etc unless asked explicitly by user.
- Don't create any authentication related file/layer unless asked explicitly.

## Application Plan & Progress Tracking

- **Check for `APPLICATION_PLAN.md`** in the root directory:
    - **IF PRESENT**: Read it first to understand the overall plan, features, and implementation roadmap.
    - **STRICTLY FOLLOW**: Align all development with the requirements and constraints defined in this plan.

- **Create or Update `IMPLEMENTATION_SUMMARY.md`** in the root directory:
    - Strictly create or update `IMPLEMENTATION_SUMMARY.md` file for implementation summary or change history after every edit you are making in the code at the end only.
    - make sure Implementation Summary is short.
    - Make sure to include the details from `APPLICATION_PLAN.md` file (if present) like what features are implemented or pending etc.
    - Do not include any technical details such as tech stack, architecture, setup instructions, technologies used, or prerequisites, only provide feature-related information

## Development Workflow

- Don't run dev server.
- Use only pnpm.
- **Important** Always read the attached files/images/references if exist first before proceeding with next steps.
- Always install dependancies if not installed before checking typescript errors or running build.
- Run pnpm build after completion of task at the end only. Don't run build command in between. Fix any errors and run build again.
- While editing exisitng code do very minimal targeted changes related to any feature or bug requested only. Don't make unnecessary changes
- Don't run any git related commands.
- Don't change anything inside eslint config, vite.config and vite plugin files strictly.
- IF attachments are provided - After doing all the required changes please verify styles, css of the application is in accordance with the attached images if provided any and check and fix if you are following prompt correctly to use the attached files, images as intended by user.

## Response language

- Strictly respond only in English language even if user explictly mentions another language in prompts.

## Tech Stack & Implementation

- Work with only tailwind css v4 whose setup is already done correctly (no verification needed).
- Mock the backend with local storage if backend is not generated.
- If backend is not generated Always simulate backend with local storage and mock data son't add any workers or external api calls for that.
- After service layer generation replace all the data fetches, data mutations from components, pages with service layer function calls which will have api calls with import.meta.env.VITE_MOCK_DATA env fallback check.
- If user tells to use attached images as logo or some static image in app copy those attached image files to public directory first and then use them in code. Only copy into public directory when exact image is to be used in application like logo or static asset image else just read the attached file for reference in code generation.
- Don't delete files from .references directory.
- Always add optional chaining `?.` after the data variables which can be undefined or null while accessing values with functions like `.map()`, `.slice()`, `.trim()` and much more. to handle undefined values and avoid runtime UI crashes.

## UI/UX Guidelines

- While making UI consider the user prompt category whether to make Professional UI / Jazzy UI / Playful UI or any other type of UI based on the prompt and considering the use of app and how app will be used by end users.
- Also always take into consideration the atttached files/image paths while building UI design if user mentions 'design from this' or 'attached image' etc.
- Make UI elegant, clean and modern.
- Body should not be scrollable horizontally at all. Ensure proper overflow handling.
- Don't change the default font and styling from index.css unless asked explicitly or unless absolutely required.
- Don't add any type of css reset over '\*' selector keep current styles as it is.
- Don't use tailwind theme from index.css file while writing tailwind classes e.g bg-background,text-forground,bg-primary,text-primary etc. unless and until custom theme is given by user.
- Use nice, minimal loaders for pending api calls or background actions (if applicable).
- **NEVER EVER CHANGE** `css @import 'tailwindcss' ` inside frontend index.css file it will break the tailwind version 4 css.

## Agent Integration (If Agents Provided)

**AGENT_CONFIGS Structure (Copy ALL fields exactly):**

- Update `src/agentSdk/agents.ts` AGENT_CONFIGS array with provided agents
- Required fields: `id`, `name`, `description`, `triggerEvents[]`, `config.appId`, `config.accountId`, `config.widgetKey`
- **CRITICAL**: `config.widgetKey` is MANDATORY - never skip/remove it
- **STRICT**: Only use triggerEvents from provided config - NEVER create new trigger events based on app logic
- Don't change anything else in agents.ts file
- Strictly follow type AgentConfig from `src/agentSdk/types.ts` for agent config object in AGENT_CONFIGS array.
- Remember trigger event type is required so add it always.
- Always add trigger type `sync` or `async` while writing `src/agentSdk/agents.ts` file.

**Trigger Event Types:**

- **Sync** (returns data): Await response, add outputSchema (zod), determine by checking if event description implies returning data
- **Async** (background): Fire and forget, no outputSchema

**emitter.emit() Usage:**

- Import: `import { emitter } from '@/agentSdk'`. Never modify `src/agentSdk/emitter.ts`
- Syntax: `emitter.emit({ agentId, event, payload, uid: user?.id ?? crypto.randomUUID() })`
- Place calls after user actions/API calls that match trigger event descriptions
- Only emit for events in provided triggerEvents array - remove old emits with unlisted events
- Document attachment (optional): `documents: [{ signedUrl, fileName?, mimeType? }]` for document-related events
- Pass `documents` only at **root level** (not inside `payload`). **Correct:** `emitter.emit({ agentId, event, payload: { ...eventData }, documents: [{ signedUrl, fileName?, mimeType? }], uid })`. **Wrong:** `payload: { documents: [...] }` — ignored by the agent executor.

**Service Layer Rules (Apply in order):**

1. **Agent sync event available?** → Remove mock/API logic, use ONLY `await emitter.emit()`, return result directly
2. **No agent sync event?** → Check `import.meta.env.VITE_USE_MOCK_DATA === "true"`, return mock from `src/data` if true, else API call
3. **Both needed? (rare)** → Keep mock/API logic, add `emitter.emit()` for side effects

**STRICT CHECKLIST TO FOLLOW WHEN HANDLING DOCUMENTS AND AGENTS (ATTACHED AGENTS) TOGETHER**

- Always ensure to upload document to backend document service first which will internally use `@uptiqai/integrations-sdk` storage layer.
- After uploading document to the backend get document signed url from storage service on the frontend side.
- After getting signed url when passing the document to attached agent make a emitter.emit sync call and pass the documents like below example.
  `const result = await emitter.emit({ agentId, event, payload: { ...eventData }, documents: [{ signedUrl, fileName?, mimeType? }], uid })` `

## Guidelines for Backend Integration (only when requested or asked for backend)

- When integrating with backend for first time start by writing the api client instance in src/lib/api.ts to connect to the backend
- Use axios api client to make api calls.
- Do not add API calls anywhere outside the src/services folder which will have module wise apis.
- If implementing features that reference or depend on other pages/components not yet created in frontend or backend, implement those prerequisite pages/features first to ensure full functionality.
- **_ONLY_** implement authentication (login, signup pages, auth handling, protected routes) when the feature involves user-specific data (user profiles, user settings, personalized content, etc.). Update API_SPECIFICATION.md accordingly with authenticated/unauthenticated endpoint details.
- Ensure all implemented features remain fully functional with proper data flow between dependent components.

### API Service Function Writing Guidelines

- Maintain the pattern of using mock data when env variable import.meta.env.VITE_USE_MOCK_DATA is equal to "true" otherwise directly call live api
- Live API Base url is import.meta.env.VITE_API_BASE_URL don't defer from that.
- Make sure API endpoint is correct as per the backend.
- Make sure request body schema (if needed) matches the backend routes.

### Authentication (Only When User Explicitly Requests)

- Only create authentication related files when explictly asked.
- If authentication is required properly use JWT accessToken and refreshToken pattern in apiClient interceptors for making authorized api calls.
- Only make those apis authenticated which are actually authenticated on backend otherwise keep them public.
- Handle accessToken expiry properly and creating new accessToken from refreshToken functionality properly using axios error interceptors on 401 error code.
- **When to implement:** ONLY when user explicitly asks for authentication
- **Default:** Email/Password authentication (login + register pages)
- **Google OAuth:** ONLY if user explicitly requests Google authentication

### Google OAuth Popup Implementation

When implementing Google OAuth authentication, **STRICTLY** use the popup pattern for developement mode checking `import.meta.env.DEV` is true or not:

**Service Layer (`authService.ts`):**

```typescript
googleLogin: () => {
    const loginUrl = `${import.meta.env.VITE_API_BASE_URL}/auth/google`;
    if (import.meta.env.DEV) {
        window.open(loginUrl, '_blank', 'width=500,height=650');
    } else {
        window.location.href = loginUrl;
    }
};
```

**Callback Component (`AuthCallback.tsx`):**

- Extract tokens from URL query params (`accessToken`, `refreshToken`)
- **STRICTLY** handle popup closing only in development i.e when `import.meta.env.DEV` is true
- Check if opened as popup using `window.opener`
- If popup: send `postMessage` to opener window and close
- Message format: `{ type: 'AUTH_SUCCESS', accessToken, refreshToken }` or `{ type: 'AUTH_ERROR', message: string }`
- Target origin: `window.location.origin`
- Fallback: if not popup, store tokens in localStorage and navigate to home

**Main App Component:**

- Add `message` event listener in `useEffect`
- Validate event origin matches `window.location.origin`
- On `AUTH_SUCCESS`: store tokens in localStorage, then redirect the user to the application's authenticated entry route using the router navigation method, OR use `window.location.reload()` if your current page handles authenticated state
- The authenticated entry route should be the main protected route of the application (e.g., root route if it handles auth-based redirection)
- On `AUTH_ERROR`: show error message to user
- Clean up listener on unmount

### Strictly Prohibited Actions

- Strictly don't use supabase client js library to connect to supabase from frontend directly even if asked by user explicitly. This will get handled by backend.
- Don't try to handle environment variables they are managed externally.
- Don't make changes in vite.config.ts

## API Integration
- Create or Update API_SPECIFICATION.md file after changes in service layer for api related changes.

## AGENT INTEGRATION 
- It can be done via 2 ways
    A) WEB SOCKET : this must be used if the task has long running task or background jobs(like docuem extraction etc) or live feedback to users
    B) API : this must be used if the task requires sync calls  with agent 
- if the agent integration requires a web socket connection only refer this @./AGENT_INTEGRATION_WEB_SOCKET.md and agentSdk/agents.ts file for implementation

## LLM Integration (AI SDK UI - Only When Requested)

**Backend:** LLM integration pre-configured. Implement the llm endpoint only when needed.

**IMPORTANT** Prohibit calling the llm models directly from the frontend.

**Frontend:** Use `@ai-sdk/react` hooks (v3.x) for streaming AI responses:

**useChat** offers real-time streaming of chat messages, abstracting state management for inputs, messages, loading, and errors, allowing for seamless integration into any UI design.

**useCompletion** enables you to handle text completions in your applications, managing the prompt input and automatically updating the UI as new completions are streamed.

Implements real-time message streaming when necessary.

### Basic Chat Implementation

```tsx
import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';
import { useState } from 'react';

const ChatComponent = () => {
    const [input, setInput] = useState('');

    const { messages, sendMessage, status } = useChat({
        transport: new DefaultChatTransport({
            api: `${import.meta.env.VITE_API_BASE_URL}/ai/chat`
        })
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (input.trim()) {
            sendMessage({ text: input });
            setInput('');
        }
    };

    // Helper to extract text from message (handles both content and parts)
    const getMessageText = (message: any): string => {
        let fullText = message.content || '';
        const parts = message.parts || [];
        if (parts.length > 0) {
            fullText = parts
                .filter((part: any) => part.type === 'text')
                .map((part: any) => part.text)
                .join('');
        }
        return fullText;
    };

    return (
        <div>
            {/* Render messages */}
            <div>
                {messages.map(message => (
                    <div key={message.id}>
                        <strong>{message.role === 'user' ? 'You' : 'AI'}:</strong>
                        <div>{getMessageText(message)}</div>
                    </div>
                ))}
            </div>

            {/* Input form */}
            <form onSubmit={handleSubmit}>
                <input
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    placeholder='Type your message...'
                    disabled={status !== 'ready'}
                />
                <button
                    type='submit'
                    disabled={status !== 'ready' || !input.trim()}
                >
                    Send
                </button>
            </form>
        </div>
    );
};
```

### With System Prompt (Initial Messages)

```tsx
const SYSTEM_PROMPT = `You are a helpful assistant.`;

const { messages, sendMessage, status } = useChat({
    transport: new DefaultChatTransport({
        api: `${import.meta.env.VITE_API_BASE_URL}/ai/chat`
    }),
    initialMessages: [{ id: 'system', role: 'system', content: SYSTEM_PROMPT } as any]
} as any);
```

### Status Handling

`status` values: `'submitted'`, `'streaming'`, `'ready'`, `'error'`

```tsx
const { status, stop } = useChat({
    transport: new DefaultChatTransport({
        api: `${import.meta.env.VITE_API_BASE_URL}/ai/chat`
    })
});

const isGenerating = status === 'submitted' || status === 'streaming';

// Show loading/streaming state
{
    isGenerating && (
        <div>
            {status === 'submitted' && <div>Thinking...</div>}
            {status === 'streaming' && <div>AI is responding...</div>}
            <button onClick={() => stop()}>Stop</button>
        </div>
    );
}
```

### Error Handling

```tsx
const { error, regenerate } = useChat({
    transport: new DefaultChatTransport({
        api: `${import.meta.env.VITE_API_BASE_URL}/ai/chat`
    })
});

{
    error && (
        <div>
            <div>Error: {error.message}</div>
            <button onClick={() => regenerate()}>Retry</button>
        </div>
    );
}
```

### File Attachments (Images/Documents)

```tsx
import { useChat } from '@ai-sdk/react';
import { useState } from 'react';

const ChatWithFiles = () => {
    const [input, setInput] = useState('');
    const [files, setFiles] = useState<FileList | undefined>();

    const { messages, sendMessage, status } = useChat({
        api: `${import.meta.env.VITE_API_BASE_URL}/ai/chat`
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (input.trim() || files) {
            sendMessage({ text: input, files });
            setInput('');
            setFiles(undefined);
        }
    };

    return (
        <div>
            {/* Render messages with file attachments */}
            {messages.map(message => (
                <div key={message.id}>
                    <strong>{message.role === 'user' ? 'You' : 'AI'}:</strong>
                    <div>
                        {message.parts.map((part, index) => {
                            if (part.type === 'text') {
                                return <span key={index}>{part.text}</span>;
                            }
                            if (part.type === 'file' && part.mediaType?.startsWith('image/')) {
                                return (
                                    <img
                                        key={index}
                                        src={part.url}
                                        alt={part.filename || 'attachment'}
                                    />
                                );
                            }
                            return null;
                        })}
                    </div>
                </div>
            ))}

            {/* Input form with file upload */}
            <form onSubmit={handleSubmit}>
                <input
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    placeholder='Type your message...'
                />
                <input
                    type='file'
                    multiple
                    onChange={e => setFiles(e.target.files || undefined)}
                />
                <button
                    type='submit'
                    disabled={status !== 'ready'}
                >
                    Send
                </button>
            </form>
        </div>
    );
};
```

### File download

- **Trigger downloads, don’t navigate:** Do not open file URLs in the same tab. Always trigger a download so the user gets a file. For signed URLs or cross-origin, fetch as blob first; set filename from `Content-Disposition` or app logic.
- **Libraries (use when the feature needs them):**
    - **file-saver** — `pnpm add file-saver`; `saveAs(blob, filename)` for triggering downloads (e.g. large files, progress). Prefer native blob + anchor for simple cases.
    - **html2canvas** — `pnpm add html2canvas`; capture a DOM node as canvas/image (e.g. “download as PNG”, “export card as image”). Use with a download helper to get a file.
    - **jspdf** — `pnpm add jspdf`; generate PDFs from HTML or data. For “export this view as PDF”, combine with **html2canvas** (canvas → image → `jspdf.addImage()`) or build the PDF from content with `jspdf` only.

Helper to trigger download from a URL. Get the URL from your **service layer** (e.g. backend returns a signed URL or download endpoint); use axios there. This helper is only for the browser download step (fetch blob → object URL → click). Callers should handle errors (try/catch or .catch()).

```tsx
async function downloadFile(url: string, filename?: string, options?: RequestInit) {
    const response = await fetch(url, { credentials: 'include', ...options });
    if (!response.ok) throw new Error(`Download failed: ${response.status}`);
    const blob = await response.blob();
    const name =
        filename ?? response.headers.get('Content-Disposition')?.match(/filename="?([^"]+)"?/)?.[1] ?? 'download';
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = name;
    a.click();
    URL.revokeObjectURL(objectUrl);
}

// Usage: get URL from service (axios), then: downloadFile(signedUrl, 'report.pdf').catch(console.error);
```

### Request-Level Options (Dynamic Config)

Pass custom headers or additional body data per request:

```tsx
const { sendMessage } = useChat({
    api: `${import.meta.env.VITE_API_BASE_URL}/ai/chat`
});

// Send with custom options
sendMessage(
    { text: input },
    {
        headers: {
            Authorization: `Bearer ${accessToken}`
        },
        body: {
            temperature: 0.7,
            userId: currentUser.id,
            maxTokens: 1000
        }
    }
);
```

### Custom Data Streaming (Advanced)

Backend can stream custom data parts alongside messages using AI SDK's data streaming API:

```tsx
import { useChat } from '@ai-sdk/react';
import { useState } from 'react';

const ChatWithCustomData = () => {
    const [weatherData, setWeatherData] = useState<any>();

    const { messages } = useChat({
        api: `${import.meta.env.VITE_API_BASE_URL}/ai/chat`,
        onData: ({ data, type }) => {
            // Handle custom data streamed from backend
            if (type === 'data-weather') {
                setWeatherData(data);
            }
        }
    });

    return (
        <div>
            {/* Display custom data */}
            {weatherData && <WeatherWidget data={weatherData} />}

            {/* Render messages with data parts */}
            {messages.map(message => (
                <div key={message.id}>
                    {message.parts.map((part, index) => {
                        if (part.type === 'text') {
                            return <span key={index}>{part.text}</span>;
                        }
                        // Custom data parts are also available in message.parts
                        if (part.type === 'data-weather') {
                            return (
                                <WeatherWidget
                                    key={index}
                                    data={part.data}
                                />
                            );
                        }
                        return null;
                    })}
                </div>
            ))}
        </div>
    );
};
```

### Real-Time Streaming Display

Show live streaming output as it arrives:

```tsx
const { messages, status } = useChat({
    transport: new DefaultChatTransport({
        api: `${import.meta.env.VITE_API_BASE_URL}/ai/chat`
    })
});

// Helper to extract text
const getMessageText = (message: any): string => {
    let fullText = message.content || '';
    const parts = message.parts || [];
    if (parts.length > 0) {
        fullText = parts
            .filter((part: any) => part.type === 'text')
            .map((part: any) => part.text)
            .join('');
    }
    return fullText;
};

// Get the last assistant message for streaming display
const lastAssistantMessage = [...messages].reverse().find(m => m.role === 'assistant');

{
    status === 'streaming' && lastAssistantMessage && (
        <div className='streaming-indicator'>
            <span>● Live</span>
            <div>{getMessageText(lastAssistantMessage)}</div>
        </div>
    );
}
```

### Backend Implementation

The backend must implement POST `/ai/chat` endpoint:

```typescript
// backend/src/routes/ai.routes.ts
import { Hono } from 'hono';
import { getInstance } from '../integrations/llm/main.ts';
import { LLMProvider } from '../integrations/llm/types.ts';
import catchAsync from '../utils/catchAsync.ts';

const aiRoutes = new Hono();

aiRoutes.post(
    '/chat',
    catchAsync(async c => {
        const body = await c.req.json();
        const { messages } = body;

        const llm = getInstance({ provider: LLMProvider.Gemini });

        const response = await llm.createStream({
            messages
        });

        return response;
    })
);

export default aiRoutes;
```

Register in `src/app.ts`:

```typescript
import aiRoutes from './routes/ai.routes.ts';

app.route('/ai', aiRoutes);
```

### Important Implementation Notes

1. **API Route**: Backend endpoint must be at `/ai/chat`

2. **DefaultChatTransport**: Always wrap the API endpoint with `DefaultChatTransport`:

    ```tsx
    transport: new DefaultChatTransport({ api: '...' });
    ```

3. **Message Format**: Messages can have either:
    - `content` property (string) - simple text message
    - `parts` property (array) - structured message with text/file parts
    - Always handle both formats using the `getMessageText` helper function

4. **Type Casting**: Use `as any` for TypeScript compatibility with flexible message formats:

    ```tsx
    initialMessages: [{ id: 'system', role: 'system', content: SYSTEM_PROMPT } as any];
    ```

5. **Backend Message Handling**: The backend LLM providers automatically handle both message formats (content string or parts array) and normalize them before sending to the AI model

6. **Status Values**: Always check `status` to disable/enable UI elements:
    - `'ready'` - Ready to send messages
    - `'submitted'` - Message sent, waiting for response
    - `'streaming'` - Currently receiving streamed response
    - `'error'` - An error occurred

7. **Error Handling**: Always handle errors and provide retry functionality using the `regenerate()` function

**Important:** Only implement chat features when explicitly requested. Don't add chat UI to every app.

## Payment Integration (Stripe - Only When User Requests)

**Backend:** Payment integration pre-configured with Stripe at `@uptiqai/integrations-sdk`. Only implement payment UI when explicitly requested.

**Prerequisites:**

- Backend must have `/payment/create-checkout-session` endpoint implemented
- Backend has `/payment/stripe/webhook` endpoint for Stripe webhooks
- No additional frontend libraries required (uses standard axios + react-router-dom)

**Implementation Steps:**

**1. Create Payment Service** `src/services/payment.service.ts`:

- Define interfaces: `CreateCheckoutSessionPayload` (amount: number in cents, currency?: string, productName: string, customerEmail?: string, metadata?: Record<string, any>), `CheckoutSession` (sessionUrl: string, sessionId: string)
- Export async function `createCheckoutSession(payload)`:
    - Always call backend API endpoint (e.g., `/payment/create-checkout-session`) and return response.data
    - **IMPORTANT**: Do NOT add mock mode check - always use real Stripe APIs
    - Backend uses `@uptiqai/integrations-sdk` Payment class to handle Stripe integration

**2. Create Success Page** `src/pages/payment/Success.tsx`:

- Use `useSearchParams()` from react-router-dom to get `session_id` query param
- Display success message with green checkmark icon and show session ID if available
- Check if opened as popup using `window.opener`
- If popup: send `postMessage` to opener window with `{ type: 'PAYMENT_SUCCESS', sessionId }`, target origin: `window.location.origin`, then close popup after 3 seconds using `setTimeout(() => window.close(), 3000)`
- If not popup: provide "Return to Home" link

**3. Create Cancel Page** `src/pages/payment/Cancel.tsx`:

- Display cancellation message with warning icon and show "No charges were made" text
- Check if opened as popup using `window.opener`
- If popup: send `postMessage` to opener window with `{ type: 'PAYMENT_CANCELLED' }`, target origin: `window.location.origin`, then close popup after 3 seconds using `setTimeout(() => window.close(), 3000)`
- If not popup: provide two buttons: "Return to Home" (Link to '/') and "Try Again" (window.history.back())

**4. Create Checkout Component** (where user initiates payment):

- Accept props: `amount: number`, `productName: string`
- State: `isLoading`, `error`
- On button click: call stripe checkout session api to create checkout session, then open in popup via `window.open(sessionUrl, "_blank", "width=800,height=800")`
- Handle errors with try/catch, display error message
- Button shows loading state while processing

**5. Update Router Configuration:**

- Add routes: `{ path: '/payment/success', element: <PaymentSuccess /> }` and `{ path: '/payment/cancel', element: <PaymentCancel /> }`

**Code Snippet - Payment Service Pattern:**

```typescript
import { api } from '@/lib/api.ts';

export async function createCheckoutSession(payload) {
    // payload.amount should be in cents (e.g., 2000 for $20.00)
    const response = await api.post('/payment/create-checkout-session', payload);
    return response.data; // { sessionUrl, sessionId }
}
```

**Code Snippet - Checkout Button Pattern:**

```typescript
const handleCheckout = async () => {
    // amount should be in cents (e.g., 2000 for $20.00)
    const { sessionUrl } = await createCheckoutSession({
        amount: 2000, // cents
        productName: 'Premium Plan',
        currency: 'usd'
    });
    window.open(sessionUrl, '_blank', 'width=800,height=800'); // Open Stripe Checkout in popup
};
```

**6. Stripe Popup Message Handling in Main App:**

Add message event listener in main app component (App.tsx) inside `useEffect`:

- Listen for `message` events on window
- Validate event origin matches `window.location.origin`
- Handle message types:
    - `PAYMENT_SUCCESS`: Refresh window using `window.location.reload()` to update app state
    - `PAYMENT_CANCELLED`: Show optional notification to user (e.g., "Payment was cancelled")
- Clean up listener on unmount: `return () => window.removeEventListener('message', handler)`

**Important Notes:**

- **Never call Stripe API directly from frontend** - Always use backend endpoint
- **Backend Integration**: Backend uses `@uptiqai/integrations-sdk` Payment class to handle Stripe
- **Always use real Stripe API** - Payments always go through Stripe test mode, even when `VITE_USE_MOCK_DATA=true`
- **Amount format**: Pass amounts in **cents** (e.g., 2000 for $20.00) to match backend API
- **Session ID**: Available as `?session_id=cs_xxx` query parameter in success URL
- **Webhook handling**: All payment status updates happen server-side at `/payment/stripe/webhook`
- **Popup pattern**: Checkout opens in popup (800x800), success/cancel pages close popup and notify parent window

**Only implement payment features when explicitly requested by the user.**

## Image Generation Integration

### Strict restrictions in image generation integration.

- Image generation intgration calls will always go to backend
- In apps with image generation enabled from ai or prompt don't give or create any ui for model or model provider selection as this is externally handled

## Whatsapp Messaging Integration (If asked only)

- **NO DIRECT WHATSAPP API CALLS FROM FRONTEND**
- Strictly don't call any real whatsapp apis directly from frontend.
- Whatsapp integrations is strictly controlled at backend with `@uptiqai/integrations-sdk`
- Frontend should always call relevant apis for whatsapp from backend only.
- Assume that backend has handled it completely.
- Also if you need to implement any type of phone number/ mobile number input on frontend ensure to add country code before the number by default.
