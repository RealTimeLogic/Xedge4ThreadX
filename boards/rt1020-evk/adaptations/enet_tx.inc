/* Copyright (C) Real Time Logic LLC, 2026.
 * Preserve NetX packet bytes and pointers while satisfying ENET DMA alignment.
 * The SDK completion path removes only the Ethernet header. Moving the native
 * packet in place leaves its IP-header pointer invalid for TCP retransmission. */
AT_NONCACHEABLE_SECTION_ALIGN(static UCHAR txFrames[NX_DRIVER_TX_DESCRIPTORS][1536], 32);

static UINT _nx_driver_hardware_packet_send(NX_PACKET* packet)
{
   ULONG index = nx_driver_information.nx_driver_information_transmit_current_index;
   enet_tx_bd_struct_t* descriptor =
      &nx_driver_information.nx_driver_information_dma_tx_descriptors[index];
   NX_PACKET* part;
   ULONG length = 0;
   if(packet->nx_packet_length > NX_DRIVER_ETHERNET_MTU ||
      (descriptor->control & ENET_BUFFDESCRIPTOR_TX_READY_MASK) ||
      nx_driver_information.nx_driver_information_transmit_packets[index])
   {
      return NX_DRIVER_ERROR;
   }
   /* ENET SHIFT16 skips the first two bytes of this aligned DMA buffer. */
   for(part = packet; part; part = part->nx_packet_next)
   {
      ULONG bytes = (ULONG)(part->nx_packet_append_ptr - part->nx_packet_prepend_ptr);
      if(bytes > NX_DRIVER_ETHERNET_MTU - length)
      {
         return NX_DRIVER_ERROR;
      }
      memcpy(txFrames[index] + 2 + length, part->nx_packet_prepend_ptr, bytes);
      length += bytes;
   }
   if(length != packet->nx_packet_length)
   {
      return NX_DRIVER_ERROR;
   }
   descriptor->buffer = (uint32_t)txFrames[index];
   descriptor->length = (uint16_t)(length + 2);
   nx_driver_information.nx_driver_information_transmit_packets[index] = packet;
   nx_driver_information.nx_driver_information_transmit_current_index =
      (index + 1) & (NX_DRIVER_TX_DESCRIPTORS - 1);
   nx_driver_information.nx_driver_information_number_of_transmit_buffers_in_use++;
   __DMB();
   descriptor->control |= ENET_BUFFDESCRIPTOR_TX_LAST_MASK | ENET_BUFFDESCRIPTOR_TX_READY_MASK;
   __DSB();
   if(!EXAMPLE_ENET->TDAR)
   {
      EXAMPLE_ENET->TDAR = ENET_TDAR_TDAR_MASK;
   }
   return NX_SUCCESS;
}
