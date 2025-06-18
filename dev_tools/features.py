from collections import defaultdict
features_loaded = False
features_obj = None

class FeatureDesc:

    def __init__(self, short, medium=None, full=None, links=None):
        self.short = short
        if medium:
            self.medium = medium
        else:
            self.medium = ""
        if full:
            self.full = full
        else:
            self.full = ""
        if links:
            self.links = links
        else:
            self.links = []

    def __str__(self):
        return self.short

class RaftFeatures:

    def __init__(self):
        self.defs = {}
        
    def simple_lookup(self, name):
        return self.defs[name]

    def add_feature(self, feat_def, replace=False):
        if feat_def.short in self.defs:
            if not replace and self.defs[feat_def.short].medium != "undefined " + feat_def.short:
                raise Exception(f'cannot replace {feat_def} when already present')
        self.defs[feat_def.short] = feat_def

    def get(self, short):
        if short not in self.defs:
            self.defs[short] = FeatureDesc(short, medium="undefined " + short)
        return self.defs[short]

class TestFeatures:

    def __init__(self, test_name):
        self.test_name = test_name
        self.used = []
        self.focused = []
        global features_loaded
        global features_obj
        if not features_loaded:
            features_obj = RaftFeatures()
            RaftUseDefs(features_obj)
            features_loaded = True
        self.features = features_obj
        
    def add_used(self, short):
        self.used.append(short)

    def add_focused(self, short):
        self.focused.append(short)

    def get_used(self):
        res = []
        for short in self.used:
            res.append(self.features.get(short))
        return res
    
    def get_focused(self):
        res = []
        for short in self.focused:
            res.append(self.features.get(short))
        return res

    def org_format(self):
        section = []
        section.append("* Raft features in test")
        all_links = {}
        for used in self.get_used():
            for link in used.links:
                all_links[link.name] = link
        for focused in self.get_focused():
            for link in focused.links:
                all_links[link.name] = link
        section.append("** Features under focus")
        for focused in self.get_focused():
            section.append(f"- {focused.short}: {focused.full}")
        section.append("")
        section.append("** Features used but not under focus")
        for used in self.get_used():
            section.append(f"- {used.short}: {used.full}")
        section.append("")
        section.append("** links to listed docs")
        for link in all_links.values():
            section.append(f"- {link.get_display_name()} - {link.get_display_link('org')}")
        section.append("")
        return section

    def rst_format(self):
        section = []
        section.append("Raft features in test")
        section.append("=====================")
        section.append("")
        all_links = {}
        for used in self.get_used():
            for link in used.links:
                all_links[link.name] = link
        for focused in self.get_focused():
            for link in focused.links:
                all_links[link.name] = link
        section.append("Features under focus")
        section.append("--------------------")
        section.append("")
        for focused in self.get_focused():
            section.append(f"* {focused.short}: {focused.full}")
        section.append("")
        section.append("Features used but not under focus")
        section.append("---------------------------------")
        section.append("")
        for used in self.get_used():
            section.append(f"* {used.short}: {used.full}")
        section.append("")
        section.append("Links to listed docs")
        section.append("--------------------")
        section.append("")
        for link in all_links.values():
            section.append(f"* {link.get_display_name()} - {link.get_display_link()}")
        section.append("")
        return section

    def flat_format(self):
        section = []
        section.append("Raft features used:")
        for used in self.get_used():
            section.append(f"\n* {used.short}")
            section.append(f"    {used.full}")
            for link in used.links:
                section.append(f"\n    * {link.get_display_name()} - {link.get_display_link()}")
            section.append("")
        section.append("")

        section.append("Raft features under focus in this test:")
        for focused in self.get_focused():
            section.append(f"\n* {focused.short}")
            section.append(f"    {focused.full}")
            for link in focused.links:
                section.append(f"\n    * {link[0]} - {link[1]}")
            section.append("")
        section.append("")
        
        return section

class FeatureLink:

    def __init__(self, name, link, target_type):
        self.name = name
        self.link = link
        self.target_type = target_type

    def get_display_name(self):
        return self.name

    def get_display_link(self, form="rst"):
        if form != "rst":
            return self.link
        if self.target_type == "external":        
            return f"`<{self.link}>`__"
        else:
            return f":ref:`{self.link}`"
    
class RaftUseDefs:

    def __init__(self, raft_features):
        self.raft_features = raft_features
        self.defs = []
        for attribute in dir(self):
            if attribute.startswith("create") and callable(getattr(self, attribute)):
                getattr(self, attribute)()

    def create_elections(self):
        links = []
        links.append(FeatureLink('thesis',"https://github.com/ongardie/dissertation/blob/master/online.pdf", 'external'))
        full = []
        full.append("The voting process of an election, followed by the TERM_START log record propogation.")
        full.append("Primary explation is in the thesis section 3.4, with the post")
        full.append("election TERM_START record mentioned only in section 6.4.1 under read only client queries")
        full = ' '.join(full)
        f1 = FeatureDesc('election', 'Normal election sequence', full, links)
        self.raft_features.add_feature(f1)

    def create_slow_follower(self):
        links = []
        links.append(FeatureLink('thesis',"https://github.com/ongardie/dissertation/blob/master/online.pdf", 'external'))
        full = []
        full.append("When a Follower has not been kept up to date with the raft log, such that its latest")
        full.append("log record index is more than one less than the Leader's latest index, it is said to be 'slow'.")
        full.append("The Leader detects this situation when the Follower rejects an append entries message.")
        full.append("In response the Leader does a 'backdown' sequence, decrementing the log record index ")
        full.append("targeting that Follower and sending that record. The Leader keeps doing this as long")
        full.append("as the Follower says no. Once the Follower says it can accept the log record, the leader")
        full.append("begins sending 'catchup' append entries. This implememtation streamlines this a bit by ")
        full.append("using the maxIndex property in the append entries response to skip the repeated backdown")
        full.append("messages. ")
        full.append("The log replication logic in thesis section 3.5 explains this, including the logic to skip")
        full.append("to the the backdown messages that would fail.")
        full = ' '.join(full)
        f1 = FeatureDesc('slow_follower', 'Leader trying to catch up slow follower', full, links)
        self.raft_features.add_feature(f1)

    def create_snapshot_replicate(self):
        links = []
        links.append(FeatureLink('thesis',"https://github.com/ongardie/dissertation/blob/master/online.pdf", 'external'))
        links.append(FeatureLink('Snapshot Process',"Snapshot Process", 'internal'))
        full = []
        full.append("When a Follower needs to receive a log record that the Leader has trimmed from the log ")
        full.append("because it was superceeded by a snapshot, the Leader recognizes that by comparing the ")
        full.append("Follower's expected record index with the stored snapshot last_index. When the condition")
        full.append("occurs the Leader sends the snapshot to the Follower. The process is documented in")
        full.append("the 'Snapshot Process' section of the documentation")
        full.append("The log compaction section of the thesis in Chapter 5 explains the options available to")
        full.append("to user and the RPC that is used for snapshot replication.")
        full = ' '.join(full)
        f1 = FeatureDesc('snapshot_replicate', 'Leader trying to catch up slow follower', full, links)
        self.raft_features.add_feature(f1)

if __name__=="__main__":

    tf = TestFeatures("a test")
    tf.add_used("election")
    tf.add_focused("snapshot_replicate")
    tf.add_focused("slow_follower")

    print("\n".join(tf.org_format()))
    print('-'*130)
    print("\n".join(tf.rst_format()))

    
                                          
    
