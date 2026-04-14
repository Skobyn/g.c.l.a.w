"use client";

/**
 * Admin page: Model Catalog.
 *
 * Manage LLM Providers and the Models registered under them.
 * Two-column layout: providers on the left, selected provider's detail
 * + models on the right.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type {
  CatalogModel,
  ModelCreate,
  ModelUpdate,
  Presets,
  Provider,
  ProviderCreate,
  ProviderSummary,
  ProviderUpdate,
} from "@/types";
import {
  ConfirmDialog,
  ErrorBanner,
  KindBadge,
  Modal,
  PROVIDER_KIND_LABELS,
} from "@/components/admin/models/shared";
import { ProviderForm } from "@/components/admin/models/provider-form";
import { ModelForm } from "@/components/admin/models/model-form";
import { PresetInstallDialog } from "@/components/admin/models/preset-install-dialog";
import { TestConnectionBadge } from "@/components/admin/models/test-connection-badge";

function ModelsContent() {
  const { getIdToken } = useAuth();

  const [providers, setProviders] = useState<ProviderSummary[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState<string | null>(
    null,
  );
  const [selectedProvider, setSelectedProvider] = useState<Provider | null>(
    null,
  );
  const [models, setModels] = useState<CatalogModel[]>([]);
  const [presets, setPresets] = useState<Presets | null>(null);

  const [loadingProviders, setLoadingProviders] = useState(true);
  const [loadingModels, setLoadingModels] = useState(false);
  const [providersError, setProvidersError] = useState<string | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [presetsError, setPresetsError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [showProviderForm, setShowProviderForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [showModelForm, setShowModelForm] = useState(false);
  const [editingModel, setEditingModel] = useState<CatalogModel | null>(null);
  const [showPresetDialog, setShowPresetDialog] = useState(false);
  const [deleteProviderTarget, setDeleteProviderTarget] =
    useState<ProviderSummary | null>(null);
  const [deleteModelTarget, setDeleteModelTarget] =
    useState<CatalogModel | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);

  const loadProviders = useCallback(async () => {
    try {
      const list = await api.listProviders();
      setProviders(list);
      setProvidersError(null);
      if (list.length > 0 && !selectedProviderId) {
        setSelectedProviderId(list[0].id);
      } else if (
        selectedProviderId &&
        !list.some((p) => p.id === selectedProviderId)
      ) {
        setSelectedProviderId(list[0]?.id ?? null);
      }
    } catch (err) {
      setProvidersError(
        err instanceof Error ? err.message : "Failed to load providers",
      );
    } finally {
      setLoadingProviders(false);
    }
  }, [api, selectedProviderId]);

  const loadPresets = useCallback(async () => {
    try {
      const p = await api.getPresets();
      setPresets(p);
      setPresetsError(null);
    } catch (err) {
      setPresetsError(
        err instanceof Error ? err.message : "Failed to load presets",
      );
    }
  }, [api]);

  const loadSelected = useCallback(async () => {
    if (!selectedProviderId) {
      setSelectedProvider(null);
      setModels([]);
      return;
    }
    setLoadingModels(true);
    try {
      const [prov, mods] = await Promise.all([
        api.getProvider(selectedProviderId),
        api.listModels(selectedProviderId),
      ]);
      setSelectedProvider(prov);
      setModels(mods);
      setModelsError(null);
    } catch (err) {
      setModelsError(
        err instanceof Error ? err.message : "Failed to load provider detail",
      );
    } finally {
      setLoadingModels(false);
    }
  }, [api, selectedProviderId]);

  useEffect(() => {
    loadProviders();
    loadPresets();
  }, [loadProviders, loadPresets]);

  useEffect(() => {
    loadSelected();
  }, [loadSelected]);

  async function handleCreateProvider(body: ProviderCreate) {
    const created = await api.createProvider(body);
    setShowProviderForm(false);
    setEditingProvider(null);
    await loadProviders();
    setSelectedProviderId(created.id);
  }

  async function handleUpdateProvider(body: ProviderUpdate) {
    if (!editingProvider) return;
    await api.updateProvider(editingProvider.id, body);
    setShowProviderForm(false);
    setEditingProvider(null);
    await loadProviders();
    await loadSelected();
  }

  async function handleToggleProviderEnabled(p: ProviderSummary) {
    try {
      await api.updateProvider(p.id, { enabled: !p.enabled });
      await loadProviders();
      if (p.id === selectedProviderId) await loadSelected();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to toggle provider",
      );
    }
  }

  async function handleDeleteProvider() {
    if (!deleteProviderTarget) return;
    setDeleteBusy(true);
    try {
      await api.deleteProvider(deleteProviderTarget.id);
      setDeleteProviderTarget(null);
      await loadProviders();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to delete provider",
      );
    } finally {
      setDeleteBusy(false);
    }
  }

  async function handleCreateModel(body: ModelCreate) {
    await api.createModel(body);
    setShowModelForm(false);
    setEditingModel(null);
    await loadSelected();
    await loadProviders();
  }

  async function handleUpdateModel(body: ModelUpdate) {
    if (!editingModel) return;
    await api.updateModel(editingModel.id, body);
    setShowModelForm(false);
    setEditingModel(null);
    await loadSelected();
  }

  async function handleToggleModelEnabled(m: CatalogModel) {
    try {
      await api.updateModel(m.id, { enabled: !m.enabled });
      await loadSelected();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to toggle model",
      );
    }
  }

  async function handleDeleteModel() {
    if (!deleteModelTarget) return;
    setDeleteBusy(true);
    try {
      await api.deleteModel(deleteModelTarget.id);
      setDeleteModelTarget(null);
      await loadSelected();
      await loadProviders();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to delete model",
      );
    } finally {
      setDeleteBusy(false);
    }
  }

  async function handleInstallPresets(
    modelIds: string[],
  ): Promise<CatalogModel[]> {
    if (!selectedProvider) return [];
    const res = await api.installPresets(selectedProvider.id, modelIds);
    await loadSelected();
    await loadProviders();
    return res.created;
  }

  const existingModelIds = useMemo(
    () => new Set(models.map((m) => m.model_id)),
    [models],
  );

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
        <div>
          <h1 className="text-2xl font-bold">Model Catalog</h1>
          <p className="mt-0.5 text-sm text-slate-400">
            Manage LLM providers and the models registered under them.
          </p>
        </div>
        <button
          onClick={() => {
            setEditingProvider(null);
            setShowProviderForm(true);
          }}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          + Add Provider
        </button>
      </header>

      <main className="flex-1 overflow-y-auto p-6">
        {actionError && (
          <div className="mb-4">
            <ErrorBanner error={actionError} />
          </div>
        )}
        {presetsError && (
          <div className="mb-4 rounded-md border border-amber-700 bg-amber-900/30 px-4 py-2 text-xs text-amber-300">
            Presets unavailable: {presetsError}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
          {/* Provider column */}
          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
              Providers
            </h2>
            <ErrorBanner error={providersError} />

            {loadingProviders ? (
              <div className="flex items-center justify-center py-16">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
              </div>
            ) : providers.length === 0 ? (
              <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-8 text-center text-sm text-slate-500">
                No providers yet — click &quot;+ Add Provider&quot; to get
                started.
              </div>
            ) : (
              <div className="space-y-2">
                {providers.map((p) => {
                  const active = p.id === selectedProviderId;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setSelectedProviderId(p.id)}
                      className={`w-full rounded-lg border px-4 py-3 text-left transition-colors ${
                        active
                          ? "border-indigo-500 bg-indigo-600/10"
                          : "border-slate-700 bg-slate-900/60 hover:bg-slate-800/60"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-slate-100">
                          {p.name}
                        </span>
                        <KindBadge kind={p.kind} />
                      </div>
                      <div className="mt-1 flex items-center justify-between text-xs text-slate-400">
                        <span>
                          {p.model_count} model{p.model_count === 1 ? "" : "s"}
                          {!p.enabled && (
                            <span className="ml-2 rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase text-slate-400">
                              disabled
                            </span>
                          )}
                        </span>
                        <div
                          className="flex items-center gap-1"
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                          role="presentation"
                        >
                          <label
                            className="flex cursor-pointer items-center gap-1 rounded px-1 text-[11px] text-slate-400 hover:text-slate-200"
                            title={p.enabled ? "Disable" : "Enable"}
                          >
                            <input
                              type="checkbox"
                              checked={p.enabled}
                              onChange={() => handleToggleProviderEnabled(p)}
                              className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900 text-indigo-500 focus:ring-indigo-500"
                            />
                            on
                          </label>
                          <button
                            type="button"
                            onClick={async () => {
                              try {
                                const full = await api.getProvider(p.id);
                                setEditingProvider(full);
                                setShowProviderForm(true);
                              } catch (err) {
                                setActionError(
                                  err instanceof Error
                                    ? err.message
                                    : "Failed to load provider",
                                );
                              }
                            }}
                            className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteProviderTarget(p)}
                            className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-red-900/40 hover:text-red-300"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {/* Detail column */}
          <section className="space-y-4">
            {!selectedProvider && !loadingModels && providers.length > 0 && (
              <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-8 text-center text-sm text-slate-500">
                Select a provider to view its models.
              </div>
            )}

            {modelsError && <ErrorBanner error={modelsError} />}

            {selectedProvider && (
              <>
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900/60 px-5 py-4">
                  <div>
                    <div className="flex items-center gap-3">
                      <h2 className="text-lg font-semibold text-slate-100">
                        {selectedProvider.name}
                      </h2>
                      <KindBadge kind={selectedProvider.kind} />
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {PROVIDER_KIND_LABELS[selectedProvider.kind]}
                      {selectedProvider.base_url && (
                        <>
                          {" · "}
                          <span className="font-mono">
                            {selectedProvider.base_url}
                          </span>
                        </>
                      )}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setShowPresetDialog(true)}
                      disabled={!presets}
                      className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                    >
                      Install from presets
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setEditingModel(null);
                        setShowModelForm(true);
                      }}
                      className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
                    >
                      + Add Model
                    </button>
                  </div>
                </div>

                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                  Models
                </h3>

                {loadingModels ? (
                  <div className="flex items-center justify-center py-10">
                    <div className="h-6 w-6 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
                  </div>
                ) : models.length === 0 ? (
                  <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-8 text-center text-sm text-slate-500">
                    No models registered under this provider yet.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {models.map((m) => (
                      <div
                        key={m.id}
                        className="rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-3"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-slate-100">
                                {m.display_name}
                              </span>
                              {!m.enabled && (
                                <span className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase text-slate-400">
                                  disabled
                                </span>
                              )}
                            </div>
                            <div className="mt-0.5 font-mono text-xs text-slate-500">
                              {m.model_id}
                            </div>
                            <div className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                              {m.context_window != null && (
                                <span className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-slate-300">
                                  ctx {m.context_window.toLocaleString()}
                                </span>
                              )}
                              {m.max_output_tokens != null && (
                                <span className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-slate-300">
                                  out {m.max_output_tokens.toLocaleString()}
                                </span>
                              )}
                              {m.capabilities.vision && (
                                <span className="rounded border border-blue-700 bg-blue-900/30 px-1.5 py-0.5 text-blue-300">
                                  Vision
                                </span>
                              )}
                              {m.capabilities.tools && (
                                <span className="rounded border border-purple-700 bg-purple-900/30 px-1.5 py-0.5 text-purple-300">
                                  Tools
                                </span>
                              )}
                              {m.capabilities.reasoning && (
                                <span className="rounded border border-amber-700 bg-amber-900/30 px-1.5 py-0.5 text-amber-300">
                                  Reasoning
                                </span>
                              )}
                            </div>
                            {m.notes && (
                              <p className="mt-2 text-xs text-slate-400">
                                {m.notes}
                              </p>
                            )}
                          </div>
                          <div className="flex flex-col items-end gap-2">
                            <TestConnectionBadge
                              modelId={m.id}
                              onTest={(id) => api.testModel(id)}
                            />
                            <div className="flex items-center gap-2 text-xs">
                              <label className="flex cursor-pointer items-center gap-1 text-slate-400 hover:text-slate-200">
                                <input
                                  type="checkbox"
                                  checked={m.enabled}
                                  onChange={() => handleToggleModelEnabled(m)}
                                  className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900 text-indigo-500 focus:ring-indigo-500"
                                />
                                on
                              </label>
                              <button
                                type="button"
                                onClick={() => {
                                  setEditingModel(m);
                                  setShowModelForm(true);
                                }}
                                className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                onClick={() => setDeleteModelTarget(m)}
                                className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-red-900/40 hover:text-red-300"
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      </main>

      {showProviderForm && (
        <Modal
          title={editingProvider ? "Edit provider" : "Add provider"}
          onClose={() => {
            setShowProviderForm(false);
            setEditingProvider(null);
          }}
          wide
        >
          <ProviderForm
            initial={editingProvider}
            presets={presets}
            onSubmit={
              editingProvider ? handleUpdateProvider : handleCreateProvider
            }
            onCancel={() => {
              setShowProviderForm(false);
              setEditingProvider(null);
            }}
          />
        </Modal>
      )}

      {showModelForm && selectedProvider && (
        <Modal
          title={editingModel ? "Edit model" : "Add model"}
          onClose={() => {
            setShowModelForm(false);
            setEditingModel(null);
          }}
          wide
        >
          <ModelForm
            provider={selectedProvider}
            presets={presets}
            initial={editingModel}
            onSubmit={editingModel ? handleUpdateModel : handleCreateModel}
            onCancel={() => {
              setShowModelForm(false);
              setEditingModel(null);
            }}
          />
        </Modal>
      )}

      {showPresetDialog && selectedProvider && (
        <PresetInstallDialog
          provider={selectedProvider}
          presets={presets}
          existingModelIds={existingModelIds}
          onInstall={handleInstallPresets}
          onClose={() => setShowPresetDialog(false)}
        />
      )}

      {deleteProviderTarget && (
        <ConfirmDialog
          title="Delete provider?"
          message={
            <>
              Are you sure you want to delete{" "}
              <strong>{deleteProviderTarget.name}</strong>? This will also
              delete{" "}
              <strong>
                {deleteProviderTarget.model_count} model
                {deleteProviderTarget.model_count === 1 ? "" : "s"}
              </strong>{" "}
              under this provider.
            </>
          }
          confirmLabel="Delete provider"
          onConfirm={handleDeleteProvider}
          onCancel={() => setDeleteProviderTarget(null)}
          busy={deleteBusy}
        />
      )}

      {deleteModelTarget && (
        <ConfirmDialog
          title="Delete model?"
          message={
            <>
              Delete <strong>{deleteModelTarget.display_name}</strong> (
              <span className="font-mono">{deleteModelTarget.model_id}</span>)?
            </>
          }
          confirmLabel="Delete model"
          onConfirm={handleDeleteModel}
          onCancel={() => setDeleteModelTarget(null)}
          busy={deleteBusy}
        />
      )}
    </div>
  );
}

export default function ModelsAdminPage() {
  return (
    <AppShell>
      <ModelsContent />
    </AppShell>
  );
}
