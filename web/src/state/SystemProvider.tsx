"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  ApiRequestError,
  type PublicEvent,
  type StateEnvelope,
  TrainApiClient,
} from "@/src/api/train-api-client";
import type { AutomationDocument } from "@/src/components/automation/types";
import { toSystemModel } from "@/src/model/system-mapper";
import type { ConnectionState, SystemModel } from "@/src/model/system";

const STATE_QUERY_KEY = ["system-state"] as const;

export interface SystemActions {
  setTrainSpeed(trainId: string, speed: number): Promise<void>;
  setSwitchPosition(
    hubId: string,
    switchId: string,
    target: "straight" | "diverge",
  ): Promise<void>;
  setAutomationHalted(halted: boolean): Promise<void>;
  replaceAutomation(document: AutomationDocument): Promise<AutomationDocument>;
  refresh(): Promise<void>;
}

export interface SystemContextValue {
  readonly model: SystemModel | null;
  readonly connection: ConnectionState;
  readonly refreshing: boolean;
  readonly error: string | null;
  readonly liveUpdateError: string | null;
  readonly commandError: string | null;
  readonly pendingResources: ReadonlySet<string>;
  readonly actions: SystemActions;
}

const SystemContext = createContext<SystemContextValue | null>(null);

export function SystemProvider({ children }: { readonly children: ReactNode }) {
  const queryClient = useQueryClient();
  const apiClient = useMemo(() => new TrainApiClient(), []);
  const [pendingResources, setPendingResources] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [commandError, setCommandError] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);

  const stateQuery = useQuery<StateEnvelope>({
    queryKey: STATE_QUERY_KEY,
    queryFn: ({ signal }) => apiClient.getState(signal),
    structuralSharing: (current, incoming) =>
      latestState(
        current as StateEnvelope | undefined,
        incoming as StateEnvelope,
      ),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    refetchOnReconnect: true,
    refetchOnWindowFocus: true,
    retry: 2,
    staleTime: 1_000,
  });
  const refreshState = stateQuery.refetch;

  useEffect(
    () =>
      apiClient.subscribeToState(
        (state) => {
          setStreamError(null);
          queryClient.setQueryData<StateEnvelope>(STATE_QUERY_KEY, (current) =>
            latestState(current, state),
          );
        },
        (error) => {
          setStreamError(error.message);
          void refreshState();
        },
      ),
    [apiClient, queryClient, refreshState],
  );

  const commandMutation = useMutation({
    mutationFn: ({ event }: { event: PublicEvent }) => apiClient.publishEvent(event),
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: STATE_QUERY_KEY });
    },
  });
  const automationMutation = useMutation({
    mutationFn: (document: AutomationDocument) =>
      apiClient.replaceAutomation(document),
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: STATE_QUERY_KEY });
    },
  });

  const publish = useCallback(
    async (resource: string, event: PublicEvent) => {
      setCommandError(null);
      setPendingResources((current) => new Set(current).add(resource));
      try {
        await commandMutation.mutateAsync({ event });
      } catch (error) {
        const message =
          error instanceof ApiRequestError && error.outcomeUnknown
            ? `${error.message}. State is being refreshed before you retry.`
            : error instanceof Error
              ? error.message
              : "The command failed";
        setCommandError(message);
        throw error;
      } finally {
        setPendingResources((current) => {
          const next = new Set(current);
          next.delete(resource);
          return next;
        });
      }
    },
    [commandMutation],
  );

  const actions = useMemo<SystemActions>(
    () => ({
      setTrainSpeed: (trainId, speed) =>
        publish(`train:${trainId}`, {
          type: "set_train_speed",
          data: { train_id: trainId, speed },
        }),
      setSwitchPosition: (hubId, switchId, target) =>
        publish(`switch:${hubId}:${switchId}`, {
          type: "set_switch_position",
          data: { hub_id: hubId, switch_id: switchId, target },
        }),
      setAutomationHalted: (halted) =>
        publish("automation", {
          type: halted ? "automation_halt" : "automation_resume",
        }),
      replaceAutomation: async (document) => {
        setCommandError(null);
        setPendingResources((current) =>
          new Set(current).add("automation-document"),
        );
        try {
          return await automationMutation.mutateAsync(document);
        } catch (error) {
          setCommandError(
            error instanceof Error ? error.message : "Could not save automation",
          );
          throw error;
        } finally {
          setPendingResources((current) => {
            const next = new Set(current);
            next.delete("automation-document");
            return next;
          });
        }
      },
      refresh: async () => {
        await stateQuery.refetch();
      },
    }),
    [automationMutation, publish, stateQuery],
  );

  const model = useMemo(
    () => (stateQuery.data ? toSystemModel(stateQuery.data) : null),
    [stateQuery.data],
  );
  const connection: ConnectionState = !model
    ? stateQuery.error
      ? "offline"
      : "loading"
    : stateQuery.error
      ? "stale"
      : "online";

  const value = useMemo<SystemContextValue>(
    () => ({
      model,
      connection,
      refreshing: stateQuery.isFetching,
      error:
        stateQuery.error instanceof Error ? stateQuery.error.message : null,
      liveUpdateError: streamError,
      commandError,
      pendingResources,
      actions,
    }),
    [
      actions,
      commandError,
      connection,
      model,
      pendingResources,
      stateQuery.error,
      stateQuery.isFetching,
      streamError,
    ],
  );

  return <SystemContext.Provider value={value}>{children}</SystemContext.Provider>;
}

export function latestState(
  current: StateEnvelope | undefined,
  incoming: StateEnvelope,
): StateEnvelope {
  if (!current) {
    return incoming;
  }
  if (incoming.snapshot_at < current.snapshot_at) {
    return current;
  }
  if (
    incoming.snapshot_at === current.snapshot_at &&
    incoming.state.revision < current.state.revision
  ) {
    return current;
  }
  return incoming;
}

export function useSystem(): SystemContextValue {
  const value = useContext(SystemContext);
  if (!value) {
    throw new Error("useSystem must be used inside SystemProvider");
  }
  return value;
}
