<script setup lang="ts">
import type { MessageDetail } from '~~/shared/schemas/message'

defineProps<{ msg: MessageDetail; target: string }>()
</script>

<template>
  <nav
    class="navbar navbar-expand-md navbar-light bg-body-tertiary rounded shadow-sm navbar-msg-detail my-2"
  >
    <button
      type="button"
      class="navbar-toggler"
      data-bs-toggle="collapse"
      :data-bs-target="`#${target}`"
      aria-expanded="false"
    >
      <span class="navbar-toggler-icon"></span>
    </button>

    <div :id="target" class="collapse navbar-collapse navbar-detail px-5">
      <ul class="navbar-nav">
        <li class="nav-item" title="Previous by date">
          <a class="nav-link previous-in-list" :class="{ disabled: !msg.nav.previous_in_list }" :href="msg.nav.previous_in_list || undefined">
            <span class="fa fa-chevron-left" aria-hidden="true"></span>
          </a>
        </li>
        <li class="nav-item" title="Date Index">
          <a class="nav-link date-index" :href="msg.date_index_url">Date</a>
        </li>
        <li class="nav-item" title="Next by date">
          <a class="nav-link next-in-list" :class="{ disabled: !msg.nav.next_in_list }" :href="msg.nav.next_in_list || undefined">
            <span class="fa fa-chevron-right" aria-hidden="true"></span>
          </a>
        </li>
        <li class="nav-item" title="Previous in thread">
          <a class="nav-link previous-in-thread" :class="{ disabled: !msg.nav.previous_in_thread }" :href="msg.nav.previous_in_thread || undefined">
            <span class="fa fa-chevron-left" aria-hidden="true"></span>
          </a>
        </li>
        <li class="nav-item" title="Thread Index">
          <a class="nav-link thread-index" :href="msg.thread_index_url">Thread</a>
        </li>
        <li class="nav-item" title="Next in thread">
          <a class="nav-link next-in-thread" :class="{ disabled: !msg.nav.next_in_thread }" :href="msg.nav.next_in_thread || undefined">
            <span class="fa fa-chevron-right" aria-hidden="true"></span>
          </a>
        </li>
      </ul>
      <ul class="nav navbar-nav navbar-right"></ul>
    </div>
  </nav>
</template>
