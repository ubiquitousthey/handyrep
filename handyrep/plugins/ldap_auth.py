# authenticates against an
# LDAP server.  all users are assumed to be in
# a specific LDAP group.  The below was tested to
# work with Microsoft AD/LDAP, so it might need changes
# to generically support other kinds of LDAP servers

# this auth module requires the dictionary lookup password
# to be stored in plain text in the configuration file
# since the alternative is to make users log in with their CN, we do it anyway

# requires python_ldap module

import ldap

from plugins.handyrepplugin import HandyRepPlugin

class ldap_auth(HandyRepPlugin):

    def run(self, username, userpass, funcname=None):

        myconf = self.get_myconf()

        group = myconf["hr_group"]

        users = search_for_user(username)
        if not users:
            return self.exit_log("User %s not found" % username)
        elif len(users) > 1:
            return self.exit_log("More than one user found for %s" % username)
        else:
            user = users[0]

        if not is_user_in_group(user, group):
            return self.exit_log('Error: %s is not in group %s.' % (username, group)

        if not authenticate(user, password):
            return self.exit_log("Incorrect password for %s" % user)
        else:
            return self.exit_log("Authenticated")


    def test(self):
        if self.failed(self.test_plugin_conf("ldap_auth","ro_function_list")):
            return self.rd(False, "plugin ldap_auth is not correctly configured")
        else:
            return self.rd(False, "passwords not set for simple_password_auth")


    def exit_log (self, success, message):
        myconf = self.get_myconf()
        if success:
            if is_true(myconf["log_auth"]):
                self.log("AUTH", "user %s authenticated" % username)

            return self.rd(success, message)
        else:
            self.log("AUTH", "user %s failed to authenticate", is_true(myconf["log_auth"])
            
            if is_true(myconf["debug_auth"]):
                return self.rd(success, message)
            else:
                return self.rd(success, "Authentication Failed")


    def search_for_user(username):
        """
        Search for a user by username (e.g., 'qweaver').
        Return the a list of matching LDAP objects.
        Normally there will be just one matching object, representing the
        requested user.

        """
        myconf = self.get_myconf()
        user_dn = 'cn=Users,' + myconf["base_dn"]
        
        l = ldap.initialize(myconf["uri"])
        l.bind_s(myconf["bind_dn"], myconf["bind_password"])
        matching_users = l.search_s(
            user_dn,
            ldap.SCOPE_SUBTREE,
            filterstr='(samaccountname={un})'.format(un=username)
            )
        return matching_users


    def dump_user(user):
        """
        Take an LDAP user object and return is as a pretty-printed string.
        Example usage:

        user_list = search_for_user('qweaver')
        user = user_list[0]
        print dump_user(user)

        """
        myconf = self.get_myconf()
        cn = user[0]
        fields = user[1]

        print 'Found user "{cn}":\n-----'.format(cn = cn)
        for key in sorted(fields.keys()):
            print key, '=', fields[key]


    def is_user_in_group(user, group):
        """
        Take an LDAP user object and a group name. Return True if the user
        is in the group, False otherwise.

        """

        cn = user[0]
        fields = user[1]
        myconf = self.get_myconf()

        memberships = None
        try:
            memberships = fields['memberOf']
        except KeyError:
            # The user isn't a member of *any* groups.
            return False

        group_dn = "CN=%s,OU=Groups,%s" % ( group, myconf["base_dn"] )

        for mem in memberships:
            # Bit of hard-coding here.
            if mem == group_dn:
                return True
        return False


    def authenticate(user, password):
        """
        Take an LDAP user object and a cleartext password string.
        Return True if AD successfully authenticates the user with the password,
        False otherwise.

        """
        myconf = self.get_myconf()
        l = ldap.initialize(myconf["uri"])

        fields = user[1]
        dn = fields['distinguishedName'][0]

        try:
            l.bind_s(dn, password)
        except ldap.LDAPError as lde:
            print "LDAP authen failed for user '{dn}'. Exception says:\n{desc}\n".format(
                dn=dn,
                desc=lde.message['desc'],
                )
            return False
        else:
            return True

