import socket
import struct
import netifaces
import threading
import traceback

import ipaddress

from RWLock.RWLock import RWLockWrite
import Main

from tree.tree_if_upstream import *
from tree.tree_if_downstream import *
from tree.KernelEntry import KernelEntry


class Kernel:
    # MRT
    MRT_BASE    = 200
    MRT_INIT    = (MRT_BASE)      # /* Activate the kernel mroute code 	*/
    MRT_DONE    = (MRT_BASE + 1)  # /* Shutdown the kernel mroute		*/
    MRT_ADD_VIF = (MRT_BASE + 2)  # /* Add a virtual interface		    */
    MRT_DEL_VIF = (MRT_BASE + 3)  # /* Delete a virtual interface		*/
    MRT_ADD_MFC = (MRT_BASE + 4)  # /* Add a multicast forwarding entry	*/
    MRT_DEL_MFC = (MRT_BASE + 5)  # /* Delete a multicast forwarding entry	*/
    MRT_VERSION = (MRT_BASE + 6)  # /* Get the kernel multicast version	*/
    MRT_ASSERT  = (MRT_BASE + 7)  # /* Activate PIM assert mode		    */
    MRT_PIM     = (MRT_BASE + 8)  # /* enable PIM code			        */
    MRT_TABLE   = (MRT_BASE + 9)  # /* Specify mroute table ID		    */
    #MRT_ADD_MFC_PROXY = (MRT_BASE + 10)  # /* Add a (*,*|G) mfc entry	*/
    #MRT_DEL_MFC_PROXY = (MRT_BASE + 11)  # /* Del a (*,*|G) mfc entry	*/
    #MRT_MAX = (MRT_BASE + 11)


    # Max Number of Virtual Interfaces
    MAXVIFS = 32

    # SIGNAL MSG TYPE
    IGMPMSG_NOCACHE = 1
    IGMPMSG_WRONGVIF = 2
    IGMPMSG_WHOLEPKT = 3  # NOT USED ON PIM-DM


    # Interface flags
    VIFF_TUNNEL      = 0x1  # IPIP tunnel
    VIFF_SRCRT       = 0x2  # NI
    VIFF_REGISTER    = 0x4  # register vif
    VIFF_USE_IFINDEX = 0x8  # use vifc_lcl_ifindex instead of vifc_lcl_addr to find an interface

    def __init__(self):
        # Kernel is running
        self.running = True

        # KEY : interface_ip, VALUE : vif_index
        self.vif_dic = {}
        self.vif_index_to_name_dic = {}
        self.vif_name_to_index_dic = {}

        # KEY : (source_ip, group_ip), VALUE : KernelEntry ???? TODO
        self.routing = {}

        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IGMP)

        # MRT INIT
        s.setsockopt(socket.IPPROTO_IP, Kernel.MRT_INIT, 1)

        # MRT PIM
        s.setsockopt(socket.IPPROTO_IP, Kernel.MRT_PIM, 0)
        s.setsockopt(socket.IPPROTO_IP, Kernel.MRT_ASSERT, 1)

        self.socket = s
        self.rwlock = RWLockWrite()
        self.interface_lock = Lock()

        # Create register interface
        # todo useless in PIM-DM... useful in PIM-SM
        #self.create_virtual_interface("0.0.0.0", "pimreg", index=0, flags=Kernel.VIFF_REGISTER)

        # Create virtual interfaces
        '''
        interfaces = netifaces.interfaces()
        for interface in interfaces:
            try:
                # ignore localhost interface
                if interface == 'lo':
                    continue
                addrs = netifaces.ifaddresses(interface)
                addr = addrs[netifaces.AF_INET][0]['addr']
                self.create_virtual_interface(ip_interface=addr, interface_name=interface)
            except Exception:
                continue
        '''

        self.pim_interface = {} # name: interface_pim
        self.igmp_interface = {}  # name: interface_igmp

        # receive signals from kernel with a background thread
        handler_thread = threading.Thread(target=self.handler)
        handler_thread.daemon = True
        handler_thread.start()

    '''
    Structure to create/remove virtual interfaces
    struct vifctl {
        vifi_t	vifc_vifi;		        /* Index of VIF */
        unsigned char vifc_flags;	    /* VIFF_ flags */
        unsigned char vifc_threshold;	/* ttl limit */
        unsigned int vifc_rate_limit;	/* Rate limiter values (NI) */
        union {
            struct in_addr vifc_lcl_addr;     /* Local interface address */
            int            vifc_lcl_ifindex;  /* Local interface index   */
        };
        struct in_addr vifc_rmt_addr;	/* IPIP tunnel addr */
    };
    '''
    '''
    def create_virtual_interface(self, ip_interface: str or bytes, interface_name: str, flags=0x0):
        with self.interface_lock:
            index = list(range(0, self.MAXVIFS) - self.vif_index_to_name_dic.keys())[0]


            if type(ip_interface) is str:
                ip_interface = socket.inet_aton(ip_interface)

            struct_mrt_add_vif = struct.pack("HBBI 4s 4s", index, flags, 1, 0, ip_interface, socket.inet_aton("0.0.0.0"))
            self.socket.setsockopt(socket.IPPROTO_IP, Kernel.MRT_ADD_VIF, struct_mrt_add_vif)
            self.vif_dic[socket.inet_ntoa(ip_interface)] = index
            self.vif_index_to_name_dic[index] = interface_name
            self.vif_name_to_index_dic[interface_name] = index


            with self.rwlock.genWlock():
                for kernel_entry in list(self.routing.values()):
                    kernel_entry.new_interface(index)

            return index
    '''



######################### new create virtual if
    def create_virtual_interface(self, ip_interface: str or bytes, interface_name: str, index, flags=0x0):
        #with self.interface_lock:
        if type(ip_interface) is str:
            ip_interface = socket.inet_aton(ip_interface)

        struct_mrt_add_vif = struct.pack("HBBI 4s 4s", index, flags, 1, 0, ip_interface,
                                         socket.inet_aton("0.0.0.0"))
        self.socket.setsockopt(socket.IPPROTO_IP, Kernel.MRT_ADD_VIF, struct_mrt_add_vif)
        self.vif_dic[socket.inet_ntoa(ip_interface)] = index
        self.vif_index_to_name_dic[index] = interface_name
        self.vif_name_to_index_dic[interface_name] = index

        with self.rwlock.genWlock():
            for kernel_entry in list(self.routing.values()):
                kernel_entry.new_interface(index)

        return index


    def create_pim_interface(self, interface_name: str, state_refresh_capable:bool):
        from InterfacePIM import InterfacePim
        with self.interface_lock:
            pim_interface = self.pim_interface.get(interface_name)
            igmp_interface = self.igmp_interface.get(interface_name)
            vif_already_exists = pim_interface or igmp_interface
            if pim_interface:
                # already exists
                return
            elif igmp_interface:
                index = igmp_interface.vif_index
            else:
                index = list(range(0, self.MAXVIFS) - self.vif_index_to_name_dic.keys())[0]

            ip_interface = None
            if interface_name not in self.pim_interface:
                pim_interface = InterfacePim(interface_name, index, state_refresh_capable)
                self.pim_interface[interface_name] = pim_interface
                ip_interface = pim_interface.ip_interface

            if not vif_already_exists:
                self.create_virtual_interface(ip_interface=ip_interface, interface_name=interface_name, index=index)

    def create_igmp_interface(self, interface_name: str):
        from InterfaceIGMP import InterfaceIGMP
        with self.interface_lock:
            pim_interface = self.pim_interface.get(interface_name)
            igmp_interface = self.igmp_interface.get(interface_name)
            vif_already_exists = pim_interface or igmp_interface
            if igmp_interface:
                # already exists
                return
            elif pim_interface:
                index = pim_interface.vif_index
            else:
                index = list(range(0, self.MAXVIFS) - self.vif_index_to_name_dic.keys())[0]

            ip_interface = None
            if interface_name not in self.igmp_interface:
                igmp_interface = InterfaceIGMP(interface_name, index)
                self.igmp_interface[interface_name] = igmp_interface
                ip_interface = igmp_interface.ip_interface

            if not vif_already_exists:
                self.create_virtual_interface(ip_interface=ip_interface, interface_name=interface_name, index=index)



    '''
    def create_interface(self, interface_name: str, igmp:bool = False, pim:bool = False):
        from InterfaceIGMP import InterfaceIGMP
        from InterfacePIM import InterfacePim
        if (not igmp and not pim):
            return
        with self.interface_lock:
            pim_interface = self.pim_interface.get(interface_name)
            igmp_interface = self.igmp_interface.get(interface_name)
            vif_already_exists = pim_interface or igmp_interface
            if pim_interface:
                index = pim_interface.vif_index
            elif igmp_interface:
                index = igmp_interface.vif_index
            else:
                index = list(range(0, self.MAXVIFS) - self.vif_index_to_name_dic.keys())[0]

            ip_interface = None
            if pim and interface_name not in self.pim_interface:
                pim_interface = InterfacePim(interface_name, index)
                self.pim_interface[interface_name] = pim_interface
                ip_interface = pim_interface.ip_interface
            if igmp and interface_name not in self.igmp_interface:
                igmp_interface = InterfaceIGMP(interface_name, index)
                self.igmp_interface[interface_name] = igmp_interface
                ip_interface = igmp_interface.ip_interface


            if not vif_already_exists:
                self.create_virtual_interface(ip_interface=ip_interface, interface_name=interface_name, index=index)
    '''



    def remove_interface(self, interface_name, igmp:bool=False, pim:bool=False):
        with self.interface_lock:
            ip_interface = None
            pim_interface = self.pim_interface.get(interface_name)
            igmp_interface = self.igmp_interface.get(interface_name)
            if (igmp and not igmp_interface) or (pim and not pim_interface) or (not igmp and not pim):
                return
            if pim:
                pim_interface = self.pim_interface.pop(interface_name)
                ip_interface = pim_interface.ip_interface
                pim_interface.remove()
            elif igmp:
                igmp_interface = self.igmp_interface.pop(interface_name)
                ip_interface = igmp_interface.ip_interface
                igmp_interface.remove()

            if (not self.igmp_interface.get(interface_name) and not self.pim_interface.get(interface_name)):
                self.remove_virtual_interface(ip_interface)






    def remove_virtual_interface(self, ip_interface):
        #with self.interface_lock:
        index = self.vif_dic[ip_interface]
        struct_vifctl = struct.pack("HBBI 4s 4s", index, 0, 0, 0, socket.inet_aton("0.0.0.0"), socket.inet_aton("0.0.0.0"))

        self.socket.setsockopt(socket.IPPROTO_IP, Kernel.MRT_DEL_VIF, struct_vifctl)

        del self.vif_dic[ip_interface]
        del self.vif_name_to_index_dic[self.vif_index_to_name_dic[index]]
        del self.vif_index_to_name_dic[index]
        # TODO alterar MFC's para colocar a 0 esta interface

        with self.rwlock.genWlock():
            for kernel_entry in list(self.routing.values()):
                kernel_entry.remove_interface(index)




    '''
    /* Cache manipulation structures for mrouted and PIMd */
    struct mfcctl {
        struct in_addr mfcc_origin;		    /* Origin of mcast	*/
        struct in_addr mfcc_mcastgrp;		/* Group in question	*/
        vifi_t mfcc_parent; 			    /* Where it arrived	*/
        unsigned char mfcc_ttls[MAXVIFS];	/* Where it is going	*/
        unsigned int mfcc_pkt_cnt;		    /* pkt count for src-grp */
        unsigned int mfcc_byte_cnt;
        unsigned int mfcc_wrong_if;
        int mfcc_expire;
    };
    '''
    def set_multicast_route(self, kernel_entry: KernelEntry):
        source_ip = socket.inet_aton(kernel_entry.source_ip)
        print("============")
        print(type(kernel_entry.group_ip))
        print(kernel_entry.group_ip)
        print("============")
        group_ip = socket.inet_aton(kernel_entry.group_ip)

        outbound_interfaces = kernel_entry.get_outbound_interfaces_indexes()
        if len(outbound_interfaces) != Kernel.MAXVIFS:
            raise Exception

        #outbound_interfaces_and_other_parameters = list(kernel_entry.outbound_interfaces) + [0]*4
        outbound_interfaces_and_other_parameters = outbound_interfaces + [0]*4

        #outbound_interfaces, 0, 0, 0, 0 <- only works with python>=3.5
        #struct_mfcctl = struct.pack("4s 4s H " + "B"*Kernel.MAXVIFS + " IIIi", source_ip, group_ip, inbound_interface_index, *outbound_interfaces, 0, 0, 0, 0)
        struct_mfcctl = struct.pack("4s 4s H " + "B"*Kernel.MAXVIFS + " IIIi", source_ip, group_ip, kernel_entry.inbound_interface_index, *outbound_interfaces_and_other_parameters)
        self.socket.setsockopt(socket.IPPROTO_IP, Kernel.MRT_ADD_MFC, struct_mfcctl)

        # TODO: ver melhor tabela routing
        #self.routing[(socket.inet_ntoa(source_ip), socket.inet_ntoa(group_ip))] = {"inbound_interface_index": inbound_interface_index, "outbound_interfaces": outbound_interfaces}


    def remove_multicast_route(self, kernel_entry: KernelEntry):
        source_ip = socket.inet_aton(kernel_entry.source_ip)
        group_ip = socket.inet_aton(kernel_entry.group_ip)
        outbound_interfaces_and_other_parameters = [0] + [0]*Kernel.MAXVIFS + [0]*4

        struct_mfcctl = struct.pack("4s 4s H " + "B"*Kernel.MAXVIFS + " IIIi", source_ip, group_ip, *outbound_interfaces_and_other_parameters)

        self.socket.setsockopt(socket.IPPROTO_IP, Kernel.MRT_DEL_MFC, struct_mfcctl)
        self.routing.pop((kernel_entry.source_ip, kernel_entry.group_ip))

    def exit(self):
        self.running = False

        # MRT DONE
        self.socket.setsockopt(socket.IPPROTO_IP, Kernel.MRT_DONE, 1)
        self.socket.close()


    '''
    /* This is the format the mroute daemon expects to see IGMP control
    * data. Magically happens to be like an IP packet as per the original
    */
    struct igmpmsg {
        __u32 unused1,unused2;
        unsigned char im_msgtype;		/* What is this */
        unsigned char im_mbz;			/* Must be zero */
        unsigned char im_vif;			/* Interface (this ought to be a vifi_t!) */
        unsigned char unused3;
        struct in_addr im_src,im_dst;
    };
    '''
    def handler(self):
        while self.running:
            try:
                msg = self.socket.recv(20)
                (_, _, im_msgtype, im_mbz, im_vif, _, im_src, im_dst) = struct.unpack("II B B B B 4s 4s", msg[:20])
                print((im_msgtype, im_mbz, socket.inet_ntoa(im_src), socket.inet_ntoa(im_dst)))

                if im_mbz != 0:
                    continue

                print(im_msgtype)
                print(im_mbz)
                print(im_vif)
                print(socket.inet_ntoa(im_src))
                print(socket.inet_ntoa(im_dst))
                #print((im_msgtype, im_mbz, socket.inet_ntoa(im_src), socket.inet_ntoa(im_dst)))

                ip_src = socket.inet_ntoa(im_src)
                ip_dst = socket.inet_ntoa(im_dst)

                if im_msgtype == Kernel.IGMPMSG_NOCACHE:
                    print("IGMP NO CACHE")
                    self.igmpmsg_nocache_handler(ip_src, ip_dst, im_vif)
                elif im_msgtype == Kernel.IGMPMSG_WRONGVIF:
                    print("WRONG VIF HANDLER")
                    self.igmpmsg_wrongvif_handler(ip_src, ip_dst, im_vif)
                #elif im_msgtype == Kernel.IGMPMSG_WHOLEPKT:
                #    print("IGMP_WHOLEPKT")
                #    self.igmpmsg_wholepacket_handler(ip_src, ip_dst)
                else:
                    raise Exception
            except Exception:
                traceback.print_exc()
                continue

    # receive multicast (S,G) packet and multicast routing table has no (S,G) entry
    def igmpmsg_nocache_handler(self, ip_src, ip_dst, iif):
        source_group_pair = (ip_src, ip_dst)
        """
        with self.rwlock.genWlock():
            if source_group_pair in self.routing:
                kernel_entry = self.routing[(ip_src, ip_dst)]
            else:
                kernel_entry = KernelEntry(ip_src, ip_dst, iif)
                self.routing[(ip_src, ip_dst)] = kernel_entry
                self.set_multicast_route(kernel_entry)
            kernel_entry.recv_data_msg(iif)
        """
        """
        with self.rwlock.genRlock():
            if source_group_pair in self.routing:
                kernel_entry = self.routing[(ip_src, ip_dst)]

        with self.rwlock.genWlock():
            if source_group_pair in self.routing:
                kernel_entry = self.routing[(ip_src, ip_dst)]
            else:
                kernel_entry = KernelEntry(ip_src, ip_dst, iif)
                self.routing[(ip_src, ip_dst)] = kernel_entry
                self.set_multicast_route(kernel_entry)

            kernel_entry.recv_data_msg(iif)
        """
        self.get_routing_entry(source_group_pair, create_if_not_existent=True).recv_data_msg(iif)

    # receive multicast (S,G) packet in a outbound_interface
    def igmpmsg_wrongvif_handler(self, ip_src, ip_dst, iif):
        #kernel_entry = self.routing[(ip_src, ip_dst)]
        source_group_pair = (ip_src, ip_dst)
        self.get_routing_entry(source_group_pair, create_if_not_existent=True).recv_data_msg(iif)
        #kernel_entry.recv_data_msg(iif)


    ''' useless in PIM-DM... useful in PIM-SM
    def igmpmsg_wholepacket_handler(self, ip_src, ip_dst):
        #kernel_entry = self.routing[(ip_src, ip_dst)]
        source_group_pair = (ip_src, ip_dst)
        self.get_routing_entry(source_group_pair, create_if_not_existent=True).recv_data_msg()
        #kernel_entry.recv_data_msg(iif)
    '''



    """
    def get_routing_entry(self, source_group: tuple):
        with self.rwlock.genRlock():
            return self.routing[source_group]
    """
    def get_routing_entry(self, source_group: tuple, create_if_not_existent=True):
        ip_src = source_group[0]
        ip_dst = source_group[1]
        with self.rwlock.genRlock():
            if source_group in self.routing:
                return self.routing[(ip_src, ip_dst)]

        with self.rwlock.genWlock():
            if source_group in self.routing:
                return self.routing[(ip_src, ip_dst)]
            elif create_if_not_existent:
                kernel_entry = KernelEntry(ip_src, ip_dst, 0)
                self.routing[source_group] = kernel_entry
                kernel_entry.change()
                #self.set_multicast_route(kernel_entry)
                return kernel_entry
            else:
                return None


    def notify_unicast_changes(self, subnet):
        # todo
        with self.rwlock.genWlock():
            for (source_ip, group) in self.routing.keys():
                source_ip_obj = ipaddress.ip_address(source_ip)
                if source_ip_obj in subnet:
                    self.routing[(source_ip, group)].network_update()
                    print(source_ip)

        pass

    # When interface changes number of neighbors verify if olist changes and prune/forward respectively
    def interface_change_number_of_neighbors(self):
        with self.rwlock.genWlock():
            for entry in self.routing.values():
                entry.change_at_number_of_neighbors()