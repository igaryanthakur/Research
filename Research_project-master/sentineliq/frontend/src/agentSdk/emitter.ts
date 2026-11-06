import axios from 'axios';
import { AGENT_CONFIGS } from './agents';
import { z } from 'zod';
import { v4 as uuid } from 'uuid';
import type { AgentConfig } from './types';

const agentApi = axios.create({
    baseURL: import.meta.env.VITE_AGENT_BASE_URL, // Replace with your agent API base URL
    headers: { 'Content-Type': 'application/json' }
});
const callAgent = async (params: {
    event: string;
    payload?: any;
    documents?: { signedUrl: string; fileName?: string; mimeType?: string }[];
    agentId: string;
    config: AgentConfig['config'];
    eventConfig?: AgentConfig['triggerEvents'][number];
    uid?: string;
}) => {
    const { agentId, event, payload, config, eventConfig, documents, uid = uuid() } = params;
    let message = `Event ${event} happened.`;
    try {
        // Passing output schema in message
        if (eventConfig && 'outputSchema' in eventConfig) {
            const jsonSchema = z.toJSONSchema(eventConfig.outputSchema);
            delete jsonSchema.$schema;
            delete jsonSchema.additionalProperties;
            message += ` Strictly give output in the following json schema format: ${JSON.stringify(jsonSchema)}`;
        }

        const agentResponse = await agentApi.get(`/agent-executor/agents/${agentId}`, {
            headers: {
                'app-id': config.appId,
                'account-id': config.accountId,
                'widgetkey': config.widgetKey
            }
        });
        const agent = agentResponse.data?.data;
        const agentExecutorVersion = agent?.config?.agentExecutorVersion;

        // calling agent trigger api
        const res = await agentApi.post(
            `/agent-executor${agentExecutorVersion ? `/${agentExecutorVersion}` : ''}/agents/${agentId}/trigger`,
            { message, payload, executionMode: eventConfig?.type || 'async', documents, uid },
            {
                headers: {
                    'app-id': config.appId,
                    'account-id': config.accountId,
                    'widgetkey': config.widgetKey
                }
            }
        );

        const eventType = eventConfig?.type || 'async';
        if (eventType === 'async') return res.data;

        // parsing output based on output schema for sync calls
        if (eventConfig && 'outputSchema' in eventConfig) {
            return eventConfig.outputSchema.parse(JSON.parse(res.data?.result?.content));
        }
        return JSON.parse(res.data?.result?.content);
    } catch (error) {
        console.log(`Error calling agent ${agentId}:`, error);
    }
};

const emitEvent = (params: {
    event: string;
    payload?: any;
    documents?: { signedUrl: string; fileName?: string; mimeType?: string }[];
    agentId: string;
    uid?: string;
}) => {
    const agent = AGENT_CONFIGS.find(a => a.id === params.agentId);
    if (!agent) return;
    const eventConfig = agent.triggerEvents?.find(e => e.name === params.event);
    return callAgent({ ...params, config: agent.config, eventConfig });
};

export const emitter = {
    emit: emitEvent
};
