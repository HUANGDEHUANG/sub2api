<template>
  <div class="space-y-5">
    <div v-if="!embedded">
      <h1 class="text-2xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-3xl">{{ t('videoPlaza.title') }}</h1>
      <p class="mt-1.5 text-sm text-gray-500 dark:text-dark-400">{{ t('videoPlaza.description') }}</p>
    </div>

    <div v-if="loading" class="flex min-h-[240px] items-center justify-center">
      <div class="h-8 w-8 animate-spin rounded-full border-2 border-primary-600/25 border-t-primary-600" />
    </div>
    <div v-else-if="error" class="rounded-2xl border border-red-200 bg-red-50 px-5 py-8 text-center text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
      {{ t('videoPlaza.loadFailed') }}
    </div>
    <template v-else>
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex flex-wrap gap-2">
          <button
            v-for="group in groups"
            :key="group.id"
            type="button"
            class="rounded-full border px-3 py-1.5 text-xs font-medium transition-colors"
            :class="selectedGroup === group.id ? 'border-primary-500 bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-300' : 'border-gray-200 bg-white text-gray-500 hover:border-primary-300 dark:border-dark-700 dark:bg-dark-800/60 dark:text-dark-300'"
            @click="selectedGroup = selectedGroup === group.id ? null : group.id"
          >
            {{ group.name }}
          </button>
        </div>
        <label class="relative block sm:w-72">
          <Icon name="search" size="sm" class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input v-model="search" class="input w-full pl-9" :placeholder="t('videoPlaza.searchPlaceholder')" />
        </label>
      </div>

      <div v-if="cards.length" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        <button
          v-for="card in cards"
          :key="card.key"
          type="button"
          class="group rounded-2xl border border-gray-200 bg-white p-5 text-left shadow-card transition-all hover:-translate-y-0.5 hover:border-primary-300 hover:shadow-lg dark:border-dark-700/70 dark:bg-dark-800/60 dark:hover:border-primary-600"
          @click="selectedKey = card.key"
        >
          <div class="flex items-start justify-between gap-3">
            <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-300">
              <Icon name="play" size="md" />
            </span>
            <span class="rounded-md bg-gray-100 px-2 py-1 text-[11px] text-gray-500 dark:bg-dark-700 dark:text-dark-300">{{ card.group.platform }}</span>
          </div>
          <h2 class="mt-4 break-all text-base font-semibold text-gray-900 dark:text-white">{{ card.model.name }}</h2>
          <p class="mt-1 truncate text-xs text-gray-500 dark:text-dark-400">{{ card.group.name }}</p>
          <div class="mt-6 flex items-end justify-between gap-3">
            <div>
              <p class="text-[11px] text-gray-400 dark:text-dark-500">{{ t('videoPlaza.startingPrice') }}</p>
              <p class="mt-1 font-mono text-lg font-semibold text-primary-600 dark:text-primary-300">
                ${{ formatPrice(card.startingPrice) }}<span class="ml-1 text-xs font-normal text-gray-400">{{ unitLabel(card.startingOffer) }}</span>
              </p>
            </div>
            <span class="text-xs text-gray-400 transition-colors group-hover:text-primary-500">{{ t('videoPlaza.viewDetails') }} →</span>
          </div>
        </button>
      </div>
      <div v-else class="rounded-2xl border border-dashed border-gray-300 px-5 py-12 text-center text-sm text-gray-500 dark:border-dark-600 dark:text-dark-400">{{ t('videoPlaza.empty') }}</div>

      <Teleport to="body">
        <div v-if="selectedCard" class="fixed inset-0 z-50" role="presentation" @click="closeDetails">
          <div class="absolute inset-0 bg-gray-950/40 backdrop-blur-[2px]" aria-hidden="true" />
          <aside
            class="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col overflow-hidden border-l border-gray-200 bg-white shadow-2xl dark:border-dark-700 dark:bg-dark-900"
            role="dialog"
            aria-modal="true"
            :aria-label="selectedCard.model.name"
            @click.stop
          >
            <header class="flex items-start justify-between gap-4 border-b border-gray-100 px-5 py-4 dark:border-dark-700/60">
              <div class="min-w-0">
                <h2 class="break-all text-lg font-semibold text-gray-900 dark:text-white">{{ selectedCard.model.name }}</h2>
                <p class="mt-1 text-xs text-gray-500 dark:text-dark-400">{{ selectedCard.group.name }} · {{ selectedCard.group.platform }}</p>
              </div>
              <button type="button" class="btn btn-secondary shrink-0" @click="closeDetails">{{ t('videoPlaza.backToList') }}</button>
            </header>
            <div class="min-h-0 flex-1 divide-y divide-gray-100 overflow-y-auto dark:divide-dark-700/60">
              <div v-for="(offer, index) in selectedCard.model.offers" :key="`${offer.group_id}-${index}`" class="px-5 py-4">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <span class="text-sm font-medium text-gray-800 dark:text-gray-100">{{ offer.group_name }}</span>
                  <span class="text-xs text-gray-400">{{ unitLabel(offer) }} · ×{{ formatPrice(offer.rate_multiplier) }}</span>
                </div>
                <div v-if="offer.tiers?.length" class="mt-3 grid gap-2 sm:grid-cols-2">
                  <div v-for="tier in offer.tiers" :key="tier.label" class="rounded-lg bg-gray-50 px-3 py-2 dark:bg-dark-800">
                    <p class="truncate text-[11px] text-gray-400 dark:text-dark-500" :title="formatVideoTierLabel(tier.label)">{{ formatVideoTierLabel(tier.label) }}</p>
                    <p class="mt-1 font-mono text-sm font-semibold text-gray-900 dark:text-white">${{ formatPrice(tier.price) }}</p>
                  </div>
                </div>
                <p v-else class="mt-3 font-mono text-sm font-semibold text-gray-900 dark:text-white">${{ formatPrice(offer.default_price ?? 0) }}</p>
              </div>
            </div>
            <p class="border-t border-gray-100 px-5 py-3 text-xs text-gray-400 dark:border-dark-700/60 dark:text-dark-500">{{ t('videoPlaza.priceNote') }}</p>
          </aside>
        </div>
      </Teleport>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/icons/Icon.vue'
import type { VideoPlazaGroup, VideoPlazaModel, VideoPlazaOffer } from '@/api/videoModelPlaza'

const props = defineProps<{ groups: VideoPlazaGroup[]; loading: boolean; error?: boolean; embedded?: boolean }>()
const { t } = useI18n()
const selectedGroup = ref<number | null>(null)
const selectedKey = ref<string | null>(null)
const search = ref('')

const cards = computed(() => props.groups.flatMap(group => group.models
  .filter(() => !selectedGroup.value || group.id === selectedGroup.value)
  .filter(model => !search.value.trim() || `${model.name} ${group.name}`.toLowerCase().includes(search.value.trim().toLowerCase()))
  .map(model => ({ key: `${group.id}:${model.name}`, group, model, startingOffer: cheapestOffer(model), startingPrice: cheapestPrice(model) }))))

const selectedCard = computed(() => cards.value.find(card => card.key === selectedKey.value) ?? null)

function closeDetails(): void {
  selectedKey.value = null
}

function cheapestOffer(model: VideoPlazaModel): VideoPlazaOffer {
  return model.offers.reduce((best, offer) => cheapestPrice(offer) < cheapestPrice(best) ? offer : best, model.offers[0])
}

function cheapestPrice(value: VideoPlazaModel | VideoPlazaOffer): number {
  const offers = 'offers' in value ? value.offers : [value]
  return Math.min(...offers.flatMap(offer => offer.tiers?.map(tier => tier.price) ?? [offer.default_price ?? Number.POSITIVE_INFINITY]))
}

function formatPrice(value: number): string {
  if (!Number.isFinite(value)) return '-'
  return value.toFixed(value < 0.01 ? 6 : value < 1 ? 4 : 3).replace(/0+$/, '').replace(/\.$/, '')
}

function unitLabel(offer: VideoPlazaOffer): string {
  return offer.billing_mode === 'video' ? t('videoPlaza.perSecond') : t('videoPlaza.perRequest')
}

function formatVideoTierLabel(label: string): string {
  return label.split('|', 1)[0]?.trim() || label.trim()
}
</script>
