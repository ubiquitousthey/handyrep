# plugin method for failing over connections
# using pgbouncer
# rewrites the list of databases

# plugin for users running multiple pgbouncer servers
# requires that each pgbouncer server be in the servers dictionary
# as role "pgbouncer" and enabled.

# further, this plugin requires that the handyrep user, DB and password be set
# up on pgbouncer as a valid connection string.

from plugins.handyrepplugin import HandyRepPlugin

class multi_pgbouncer(HandyRepPlugin):

    def run(self, newmaster=None):
        # used for failover of all pgbouncer servers
        if newmaster:
            master = newmaster
        else:
            master = self.get_master_name()
        blist = self.bouncer_list()
        faillist = []
        for bserv in blist:
            bpush = self.push_config(bserv, master)
            if self.failed(bpush):
                self.set_bouncer_status(bserv, "unavailable", 4, "unable to reconfigure pgbouncer server for failover")
                faillist.append(bserv)

        if faillist:
            # report failure if we couldn't reconfigure any of the servers
            return self.rd(False, "some pgbouncer servers did not change their configuration at failover: %s" % ','.join(faillist))
        else:
            return self.rd(True, "pgbouncer failover successful")

    def init(self, bouncerserver=None):
        # used to initialize proxy servers with the correct connections
        # either for just the supplied bouncer server, or for all of them
        if bouncerserver:
            blist = [bouncerserver,]
        else:
            blist = self.bouncer_list()

        master = self.get_master_name()
        faillist = []
        for bserv in blist:
            bpush = self.push_config(bserv, master)
            # if we can't push a config, then add this bouncer server to the list
            # of failed servers and mark it unavailable
            if self.failed(bpush):
                self.set_bouncer_status(bserv, "unavailable", 4, "unable to reconfigure pgbouncer server for failover")
                faillist.append(bserv)
            else:
                try:
                    pgbcn = self.connection(bserv)
                except:
                    self.set_bouncer_status(bserv, "unavailable", 4, "pgbouncer configured, but does not accept connections")
                    faillist.append(bserv)
                else:
                    pgbcn.close()
                    self.set_bouncer_status(bserv, "healthy", 1, "pgbouncer initialized")

        if faillist:
            # report failure if we couldn't reconfigure any of the servers
            return self.rd(False, "some pgbouncer servers could not be initialized: %s" % ','.join(faillist))
        else:
            return self.rd(True, "pgbouncer initialization successful")
        

    def set_bouncer_status(self, bouncerserver, status, status_no, status_message):
        self.servers[bouncerserver]["status"] = status
        self.servers[bouncerserver]["status_no"] = status_no
        self.servers[bouncerserver]["status_message"] = status_message
        self.servers[bouncerserver]["status_ts"] = self.now_string()
        return

    def push_config(self, bouncerserver, newmaster=None):
        # pushes a new config to the named pgbouncer server
        # and restarts it
        if newmaster:
            master = newmaster
        else:
            master = self.get_master_name()
        # get configuration
        dbsect = { "dbsection" : self.dbconnect_list(master), "port" : self.servers[bouncerserver]["port"] }
        # push new config
        myconf = self.conf["plugins"]["multi_pgbouncer"]
        writeconf = self.push_template(bouncerserver,myconf["template"],myconf["config_location"],dbsect,myconf["owner"])
        if self.failed(writeconf):
            return self.rd(False, "could not push new pgbouncer configuration to pgbouncer server")
        # restart pgbouncer
        restart_command = "%s -u %s -d -R %s" % (myconf["pgbouncerbin"],myconf["owner"],myconf["config_location"],)
        rsbouncer = self.run_as_root(bouncerserver,[restart_command,])
        if self.succeeded(rsbouncer):
            return self.rd(True, "pgbouncer configuration updated")
        else:
            return self.rd(False, "unable to restart pgbouncer")

    def bouncer_list(self):
        # gets a list of currently enabled pgbouncers
        blist = []
        for serv, servdeets in self.servers.iteritems():
            if servdeets["role"] == "pgbouncer" and servdeets["enabled"]:
                blist.append(serv)

        return blist


    def test(self):
        #check that we have all config variables required
        if self.failed( self.test_plugin_conf("multi_pgbouncer","pgbouncerbin","template","owner","config_location","readonly_suffix","all_replicas")):
            return self.rd(False, "multi-pgbouncer failover is not configured" )

        if self.failed( self.test_plugin_conf("multi_pgbouncer","database_list") or self.test_plugin_conf("multi_pgbouncer","databases")):
            return self.rd(False, "multi-pgbouncer failover has no configured databases" )

        #check that we can connect to the pgbouncer servers
        blist = self.bouncer_list()
        if len(blist) == 0:
            return self.rd(False, "No pgbouncer servers defined")
        
        faillist = []
        for bserv in blist:
            if self.failed(self.run_as_root(bserv,self.conf["handyrep"]["test_ssh_command"])):
                faillist.append(bserv)

        if failist:
            return self.rd(False, "cannot SSH to some pgbouncer servers: %s" % ','.join(faillist))
        
        return self.rd(True, "pgbouncer setup is correct")
    

    def poll(self, bouncerserver=None):
        if bouncerserver:
            blist = [bouncerserver,]
        else:
            blist = self.bouncer_list()

        if len(blist) == 0:
            return self.rd(False, "No pgbouncer servers defined")

        faillist = []
        for bserv in blist:
            try:
                pgbcn = self.connection(bserv)
            except:
                self.set_bouncer_status(bserv, "unavailable", 4, "pgbouncer does not accept connections")
                faillist.append(bserv)
            else:
                pgbcn.close()
                self.set_bouncer_status(bserv, "healthy", 1, "pgbouncer responding")
                
        if faillist:
            # report failure if any previously enabled bouncers are down
            return self.rd(False, "some pgbouncer servers are not responding: %s" % ','.join(faillist))
        else:
            return self.rd(True, "all pgbouncers responding")

    def dbconnect_list(self, master):
        # creates the list of database aliases and target
        # servers for pgbouncer
        # build master string first
        myconf = self.conf["plugins"]["multi_pgbouncer"]
        if myconf["databases"]:
            dbconfig = myconf["databases"]

        if myconf["database_list"]:
            dbconfig = {}
            for dbname in myconf["database_list"]:
                dbconfig[dbname] = myconf["extra_connect_param"]

        # add in the handyrep db if the user has forgotten it
        if not dbconfig.has_key(self.conf["handyrep"]["handyrep_db"]):
            dbconfig[self.conf["handyrep"]["handyrep_db"]] = myconf["extra_connect_param"]

        constr = self.dbconnect_line(dbconfig, self.servers[master]["hostname"], self.servers[master]["port"], "")
        replicas = self.sorted_replicas()
        if self.is_true(myconf["all_replicas"]):
            #if we're doing all replicas, we need to put them in as _ro0, _ro1, etc.
            # if there's no replicas, set ro1 to go to the master:
            if len(replicas) == 0 or (len(replicas) == 1 and master in replicas):
                rsuff = "%s%d" % (myconf["readonly_suffix"],1,)
                constr += self.dbconnect_line(dbconfig, self.servers[master]["hostname"], self.servers[master]["port"], rsuff)
            else:
                for rep in replicas:
                    if not rep == master:
                        rsuff = "%s%d" % (myconf["readonly_suffix"],repno,)
                        constr += self.dbconnect_line(dbconfig, self.servers[rep]["hostname"], self.servers[rep]["port"], rsuff)
                        repno += 1
        else:
            # only one readonly replica, setting it up with _ro
            if len(replicas) > 0:
                if replicas[0] == master:
                    # avoid the master
                    replicas.pop(0)
                    
            if len(replicas) > 0:
                constr += self.dbconnect_line(dbconfig, self.servers[replicas[0]]["hostname"], self.servers[replicas[0]]["port"], myconf["readonly_suffix"])
            else:
                # if no replicas, read-only connections should go to the master
                constr += self.dbconnect_line(dbconfig, self.servers[master]["hostname"], self.servers[master]["port"], myconf["readonly_suffix"])

        return constr


    def dbconnect_line(self, database_list, hostname, portno, suffix):
        confout = ""
        for dbname,nex in database_list.items():
            confout += "%s%s = dbname=%s host=%s port=%s %s \n" % (dbname, suffix, dbname, hostname, portno, nex,)

        return confout
