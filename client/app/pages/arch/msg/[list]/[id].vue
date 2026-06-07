<script setup lang="ts">
import { MessageDetailSchema } from '~~/shared/schemas/message'

definePageMeta({ layout: 'scrolling' })

const route = useRoute()
const apiPath = computed(() => `/arch/api/v1/msg/${route.params.list}/${route.params.id}/`)

const { data, error } = await useAsyncData(
  'msg-detail',
  () => useApi(apiPath.value, MessageDetailSchema),
  { watch: [apiPath] },
)

const navHidden = ref(false)

useHead({ title: () => data.value?.subject || 'Message' })
</script>

<template>
  <div class="container-fluid">
    <p v-if="error" class="mt-4">Message not found, removed, or access denied.</p>

    <template v-else-if="data">
      <DetailNavbar v-show="!navHidden" :msg="data" target="id-navbar-top" />

      <div class="row">
        <div class="msg-detail col-md-8 pt-3">
          <div v-html="data.body"></div>

          <div id="message-thread" v-html="data.thread_snippet"></div>

          <div class="d-flex justify-content-center">
            <ul id="navigation" class="list-inline">
              <li class="list-inline-item">
                <a id="toggle-nav" class="toggle" href="#" @click.prevent="navHidden = !navHidden">
                  {{ navHidden ? 'Show Navigation Bar' : 'Hide Navigation Bar' }}
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div class="msg-aside col-md-4"></div>
      </div>

      <DetailNavbar v-show="!navHidden" :msg="data" target="id-navbar-bottom" />
    </template>
  </div>
</template>
